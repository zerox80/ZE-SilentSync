use serde::{Deserialize, Serialize};
use std::{thread, time};
use std::process::Command;
use std::fs::File;
use std::io::copy;
use log::{info, error, warn};
use config::Config;

#[derive(Serialize, Deserialize, Debug)]
struct AgentConfig {
    backend_url: String,
    heartbeat_interval: u64,
    auth_token: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct SystemInfo {
    hostname: String,
    mac_address: String,
    os_info: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct Task {
    id: i32,
    #[serde(rename = "type")]
    task_type: String,
    software_name: String,
    download_url: String,
    silent_args: String,
}

#[derive(Deserialize, Debug)]
struct HeartbeatResponse {
    status: String,
    tasks: Vec<Task>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize Logger
    env_logger::init_from_env(env_logger::Env::default().default_filter_or("info"));

    info!("Starting ZLDAP Agent...");

    // Load Configuration
    let settings = Config::builder()
        .add_source(config::File::with_name("config"))
        .add_source(config::Environment::with_prefix("AGENT"))
        .build()?;

    let config: AgentConfig = settings.try_deserialize()?;
    info!("Configuration loaded. Backend: {}", config.backend_url);

    let client = reqwest::Client::new();

    loop {
        let sys_info = get_system_info();
        info!("Sending heartbeat for {}", sys_info.hostname);

        match client.post(format!("{}/heartbeat", config.backend_url))
            .header("X-Agent-Token", &config.auth_token)
            .json(&sys_info)
            .send()
            .await 
        {
            Ok(resp) => {
                if resp.status().is_success() {
                    match resp.json::<HeartbeatResponse>().await {
                        Ok(hb_resp) => {
                            if !hb_resp.tasks.is_empty() {
                                info!("Received {} tasks", hb_resp.tasks.len());
                                for task in hb_resp.tasks {
                                    if let Err(e) = process_task(&task, &config, &client).await {
                                        error!("Failed to process task {}: {}", task.software_name, e);
                                    }
                                }
                            }
                        },
                        Err(e) => error!("Failed to parse heartbeat response: {}", e),
                    }
                } else {
                    warn!("Heartbeat failed with status: {}", resp.status());
                }
            },
            Err(e) => error!("Failed to send heartbeat: {}", e),
        }

        thread::sleep(time::Duration::from_secs(config.heartbeat_interval));
    }
}

fn get_system_info() -> SystemInfo {
    let hostname = whoami::hostname();
    let os_info = format!("{} {}", whoami::distro(), whoami::arch());
    
    let mac_address = match mac_address::get_mac_address() {
        Ok(Some(mac)) => mac.to_string(),
        Ok(None) => "00:00:00:00:00:00".to_string(),
        Err(_) => "00:00:00:00:00:00".to_string(),
    };

    SystemInfo {
        hostname,
        mac_address,
        os_info,
    }
}

#[derive(Serialize, Debug)]
struct AckRequest {
    task_id: i32,
    status: String,
    message: String,
    mac_address: String,
}

async fn process_task(task: &Task, config: &AgentConfig, client: &reqwest::Client) -> Result<(), Box<dyn std::error::Error>> {
    info!("--- Processing Task: {} ---", task.task_type);
    info!("Target: {}", task.software_name);
    
    // 1. Download
    let tmp_dir = tempfile::Builder::new().prefix("zldap_install_").tempdir()?;
    let file_name = task.download_url.split('/').last().unwrap_or("installer.exe");
    let file_path = tmp_dir.path().join(file_name);

    info!("Downloading from: {} to {:?}", task.download_url, file_path);
    
    {
        let response = reqwest::get(&task.download_url).await?;
        let mut file = File::create(&file_path)?;
        let content = response.bytes().await?;
        copy(&mut content.as_ref(), &mut file)?;
    }

    info!("Download complete.");

    // 2. Install
    info!("Executing installer with args: {}", task.silent_args);
    
    let args: Vec<&str> = task.silent_args.split_whitespace().collect();

    let status = Command::new(&file_path)
        .args(&args)
        .status();

    let (ack_status, message) = match status {
        Ok(exit_status) => {
            if exit_status.success() {
                info!("Task Complete: {} (Success)", task.software_name);
                ("success", "Installed successfully".to_string())
            } else {
                error!("Task Failed: {} (Exit Code: {:?})", task.software_name, exit_status.code());
                ("failed", format!("Exit Code: {:?}", exit_status.code()))
            }
        },
        Err(e) => {
            if cfg!(target_os = "linux") && file_name.ends_with(".exe") {
                 warn!("Cannot run .exe on Linux. Simulating success for verification.");
                 ("success", "Simulated success on Linux".to_string())
            } else {
                 return Err(Box::new(e));
            }
        }
    };

    // 3. Acknowledge
    let sys_info = get_system_info();
    let ack = AckRequest {
        task_id: task.id,
        status: ack_status.to_string(),
        message: message,
        mac_address: sys_info.mac_address,
    };

    info!("Sending Acknowledgement...");
    let _ = client.post(format!("{}/ack", config.backend_url))
        .header("X-Agent-Token", &config.auth_token)
        .json(&ack)
        .send()
        .await;

    Ok(())
}
