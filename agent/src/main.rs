use serde::{Deserialize, Serialize};
use std::{thread, time};
use std::process::Command;

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
    let client = reqwest::Client::new();
    let backend_url = "http://localhost:8000/api/v1/agent"; // Configurable in real app

    println!("Starting ZLDAP Agent...");

    loop {
        let sys_info = get_system_info();
        println!("Sending heartbeat for {}", sys_info.hostname);

        match client.post(format!("{}/heartbeat", backend_url))
            .json(&sys_info)
            .send()
            .await 
        {
            Ok(resp) => {
                if resp.status().is_success() {
                    match resp.json::<HeartbeatResponse>().await {
                        Ok(hb_resp) => {
                            if !hb_resp.tasks.is_empty() {
                                println!("Received {} tasks", hb_resp.tasks.len());
                                for task in hb_resp.tasks {
                                    process_task(&task).await;
                                }
                            }
                        },
                        Err(e) => println!("Failed to parse heartbeat response: {}", e),
                    }
                } else {
                    println!("Heartbeat failed with status: {}", resp.status());
                }
            },
            Err(e) => println!("Failed to send heartbeat: {}", e),
        }

        thread::sleep(time::Duration::from_secs(10));
    }
}

fn get_system_info() -> SystemInfo {
    let hostname = whoami::hostname();
    let os_info = format!("{} {}", whoami::distro(), whoami::arch());
    
    // Simple MAC address retrieval (using first available)
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

async fn process_task(task: &Task) {
    println!("--- Processing Task: {} ---", task.task_type);
    println!("Target: {}", task.software_name);
    println!("Downloading from: {}", task.download_url);
    
    // Mock Download and Install
    thread::sleep(time::Duration::from_secs(2));
    
    println!("Executing installer with args: {}", task.silent_args);
    
    // In a real windows agent, we would use std::process::Command to run the installer
    // let status = Command::new("installer.exe").args(task.silent_args.split_whitespace()).status();
    
    thread::sleep(time::Duration::from_secs(2));
    println!("Task Complete: {}", task.software_name);
}
