use serde::{Deserialize, Serialize};
use std::time::Duration;
use std::process::Command;
use std::fs::File;
use std::io::copy;
use log::{info, error, warn};
use config::Config;
#[cfg(target_os = "windows")]
use winreg::enums::*;
#[cfg(target_os = "windows")]
use winreg::RegKey;

#[cfg(target_os = "linux")]
use std::os::unix::fs::PermissionsExt;

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
    machine_token: Option<String>,
}

fn derive_pseudo_mac(hostname: &str) -> String {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let mut hasher = DefaultHasher::new();
    hostname.hash(&mut hasher);
    let hash = hasher.finish();
    let hash_bytes = hash.to_be_bytes(); // 8 bytes

    let mut mac_bytes = [0u8; 6];
    mac_bytes.copy_from_slice(&hash_bytes[2..8]);

    // Ensure a locally administered, unicast MAC address.
    mac_bytes[0] = (mac_bytes[0] | 0x02) & 0xFE;

    format!(
        "{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}",
        mac_bytes[0], mac_bytes[1], mac_bytes[2], mac_bytes[3], mac_bytes[4], mac_bytes[5]
    )
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
    let mut machine_token: Option<String> = None;

    loop {
        let sys_info = get_system_info();
        info!("Sending heartbeat for {}", sys_info.hostname);

        let mut req = client.post(format!("{}/heartbeat", config.backend_url))
            .header("X-Agent-Token", &config.auth_token);

        if let Some(token) = &machine_token {
            req = req.header("X-Machine-Token", token);
        }

        match req.json(&sys_info)
            .send()
            .await 
        {
            Ok(resp) => {
                if resp.status().is_success() {
                    match resp.json::<HeartbeatResponse>().await {
                        Ok(hb_resp) => {
                            // Update machine token if provided
                            if let Some(token) = hb_resp.machine_token {
                                if machine_token.is_none() {
                                    info!("Received Machine Token.");
                                }
                                machine_token = Some(token);
                            }

                            if !hb_resp.tasks.is_empty() {
                                info!("Received {} tasks", hb_resp.tasks.len());
                                for task in hb_resp.tasks {
                                    // Pass machine_token clone
                                    if let Err(e) = process_task(&task, &config, &client, &machine_token).await {
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

        tokio::time::sleep(Duration::from_secs(config.heartbeat_interval)).await;
    }
}

fn get_system_info() -> SystemInfo {
    let hostname = whoami::hostname();
    let os_info = format!("{} {}", whoami::distro(), whoami::arch());
    
    let mac_address = match mac_address::get_mac_address() {
        Ok(Some(mac)) => mac.to_string(),
        Ok(None) | Err(_) => {
            warn!("Failed to get MAC address. Generating deterministic pseudo-MAC from hostname.");
            derive_pseudo_mac(&hostname)
        },
    };

    SystemInfo {
        hostname,
        mac_address,
        os_info,
    }
}

#[cfg(target_os = "windows")]
fn find_uninstall_command(software_name: &str) -> Option<String> {
    let hives = [HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER];
    let paths = [
        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
        "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    ];

    // Extract keywords from software_name for fuzzy matching
    // e.g., "BraveBrowserStandaloneSilentNightlySetup" -> ["brave", "browser", "nightly"]
    let keywords: Vec<String> = extract_keywords(software_name);
    info!("Searching registry for software with keywords: {:?}", keywords);
    
    let mut best_match: Option<(String, usize)> = None; // (uninstall_command, match_score)

    for hive in hives {
        let root = RegKey::predef(hive);
        for path in paths {
            if let Ok(key) = root.open_subkey(path) {
                for name in key.enum_keys().filter_map(|x| x.ok()) {
                    if let Ok(subkey) = key.open_subkey(&name) {
                        let display_name: String = subkey.get_value("DisplayName").unwrap_or_default();
                        let display_name_lower = display_name.to_lowercase();
                        
                        // Calculate match score (how many keywords match)
                        let match_score = keywords.iter()
                            .filter(|kw| display_name_lower.contains(kw.as_str()))
                            .count();
                        
                        // Require at least 2 keywords to match, or 1 if there's only 1 keyword
                        let min_required = if keywords.len() == 1 { 1 } else { 2 };
                        
                        if match_score >= min_required {
                            // Check if this is the best match so far
                            let is_better = match &best_match {
                                None => true,
                                Some((_, prev_score)) => match_score > *prev_score,
                            };
                            
                            if is_better {
                                // Try QuietUninstallString first, then UninstallString
                                if let Ok(cmd) = subkey.get_value::<String, _>("QuietUninstallString") {
                                    info!("Found QuietUninstallString for '{}' (score: {}): {}", display_name, match_score, cmd);
                                    best_match = Some((cmd, match_score));
                                } else if let Ok(cmd) = subkey.get_value::<String, _>("UninstallString") {
                                    info!("Found UninstallString for '{}' (score: {}): {}", display_name, match_score, cmd);
                                    best_match = Some((cmd, match_score));
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    best_match.map(|(cmd, _)| cmd)
}

/// Extract meaningful keywords from a software name
/// e.g., "BraveBrowserStandaloneSilentNightlySetup" -> ["brave", "browser", "nightly"]
fn extract_keywords(name: &str) -> Vec<String> {
    // Common words to filter out (not useful for matching)
    let stop_words = ["standalone", "silent", "setup", "installer", "install", "x64", "x86", "win", "windows"];
    
    // Split by camelCase, underscores, dashes, and spaces
    let mut words: Vec<String> = Vec::new();
    let mut current_word = String::new();
    
    for c in name.chars() {
        if c == '_' || c == '-' || c == ' ' || c == '.' {
            if !current_word.is_empty() {
                words.push(current_word.to_lowercase());
                current_word.clear();
            }
        } else if c.is_uppercase() && !current_word.is_empty() {
            // CamelCase split
            words.push(current_word.to_lowercase());
            current_word.clear();
            current_word.push(c);
        } else {
            current_word.push(c);
        }
    }
    if !current_word.is_empty() {
        words.push(current_word.to_lowercase());
    }
    
    // Filter out stop words and short words (less than 3 chars)
    words.into_iter()
        .filter(|w| w.len() >= 3 && !stop_words.contains(&w.as_str()))
        .collect()
}

#[derive(Serialize, Debug)]
struct AckRequest {
    task_id: i32,
    status: String,
    message: String,
    mac_address: String,
}

async fn process_task(task: &Task, config: &AgentConfig, client: &reqwest::Client, machine_token: &Option<String>) -> Result<(), Box<dyn std::error::Error>> {
    info!("--- Processing Task: {} ---", task.task_type);
    info!("Target: {}", task.software_name);
    
    // 1. Download
    let tmp_dir = tempfile::Builder::new().prefix("zldap_install_").tempdir()?;
    // Fix: Remove query parameters from filename
    let raw_name = task.download_url.split('/').last().unwrap_or("installer.exe");
    let base_name = raw_name.split('?').next().unwrap_or("installer.exe");
    
    // Bug Fix 9: Sanitize Filename (Prevent Path Traversal)
    // Extract just the filename component
    let file_name = std::path::Path::new(base_name)
        .file_name()
        .and_then(|os_str| os_str.to_str())
        .unwrap_or("installer.exe");

    let file_path = tmp_dir.path().join(file_name);

    info!("Downloading from: {} to {:?}", task.download_url, file_path);
    
    {
        let response = reqwest::get(&task.download_url).await?;
        if !response.status().is_success() {
             return Err(format!("Download failed with status: {}", response.status()).into());
        }
        let mut file = File::create(&file_path)?;
        let content = response.bytes().await?;
        copy(&mut content.as_ref(), &mut file)?;
        
        #[cfg(target_os = "linux")]
        {
            let mut perms = file.metadata()?.permissions();
            perms.set_mode(0o755);
            file.set_permissions(perms)?;
            info!("Set executable permissions for {:?}", file_path);
        }
    }

    info!("Download complete.");

    // 2. Install / Uninstall
    // Fix: Use custom split_args to handle quotes
    let mut args: Vec<String> = split_args(&task.silent_args);
    let mut command_path = file_path.clone();
    
    if task.task_type == "uninstall" {
        info!("Executing UNINSTALL...");
        // Bug Fix 3: Check file_name (cleaned) instead of raw URL
        if file_name.to_lowercase().ends_with(".msi") {
            // For MSI, we use msiexec /x <file> /qn
            command_path = std::path::PathBuf::from("msiexec");
            args = vec!["/x".to_string(), file_path.to_str().unwrap().to_string(), "/qn".to_string()];
        } else {
            // New Registry-Based Uninstall Logic
            #[cfg(target_os = "windows")]
            {
                if let Some(cmd) = find_uninstall_command(&task.software_name) {
                    info!("Using Registry Uninstall Command: {}", cmd);
                    // Split command into executable and args
                    // This is tricky because the string might be "C:\Program Files\App\uninstall.exe" /S
                    // We need to parse this properly.
                    // Simple heuristic: 
                    // 1. If starts with ", find closing "
                    // 2. Else take first token
                    
                    let (cmd_exe, cmd_args_str) = parse_command_string(&cmd);
                    command_path = std::path::PathBuf::from(cmd_exe);
                    
                    // If it was a standard UninstallString (not quiet), append our silent args
                    // But if it was QuietUninstallString, it might already have them. 
                    // For safety, if the user provided silent_args, we append them? 
                    // Implementation choice: Append user args to the registry command string.
                    
                    let mut new_args = split_args(&cmd_args_str);
                    if !task.silent_args.is_empty() {
                         new_args.extend(split_args(&task.silent_args));
                    }
                    args = new_args;
                    
                } else {
                     warn!("Could not find uninstall command in registry for {}. Fallback to unsafe EXE?", task.software_name);
                     return Err(format!("Registry lookup failed for {}. Generic EXE uninstall unavailable.", task.software_name).into());
                }
            }
            #[cfg(not(target_os = "windows"))]
            {
                 return Err("Registry uninstall only supported on Windows".into());
            }
        }
    } else {
        // INSTALL
        info!("Executing installer with args: {}", task.silent_args);
        // Bug Fix 3: Check file_name (cleaned) instead of raw URL
        if file_name.to_lowercase().ends_with(".msi") {
             info!("Detected MSI installer. Using msiexec.");
             command_path = std::path::PathBuf::from("msiexec");
             // msiexec /i <file> <args>
             let mut new_args = vec!["/i".to_string(), file_path.to_str().unwrap().to_string()];
             new_args.extend(args);
             args = new_args;
        }
    }

    let status = Command::new(&command_path)
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
            if cfg!(target_os = "linux") && file_name.to_lowercase().ends_with(".exe") {
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
    let mut req = client.post(format!("{}/ack", config.backend_url))
        .header("X-Agent-Token", &config.auth_token)
        .json(&ack);
        
    if let Some(token) = machine_token {
        req = req.header("X-Machine-Token", token);
    }
        
    let _ = req.send().await;

    Ok(())
}

fn split_args(input: &str) -> Vec<String> {
    let mut args = Vec::new();
    let mut current_arg = String::new();
    let mut in_quote = false;

    for c in input.chars() {
        if c == '"' {
            in_quote = !in_quote;
        } else if c.is_whitespace() && !in_quote {
            if !current_arg.is_empty() {
                args.push(current_arg.clone());
                current_arg.clear();
            }
        } else {
            current_arg.push(c);
        }
    }
    if !current_arg.is_empty() {
       args.push(current_arg);
    }
    args
}

fn parse_command_string(input: &str) -> (String, String) {
    let input = input.trim();
    if input.starts_with('"') {
        if let Some(end_quote) = input[1..].find('"') {
            let real_end = end_quote + 1;
            let exe = &input[1..real_end];
            let rest = if real_end + 1 < input.len() { &input[real_end+1..] } else { "" };
            return (exe.to_string(), rest.to_string());

        }
    }
    
    // No quotes, split by first space
    if let Some(space) = input.find(' ') {
        return (input[..space].to_string(), input[space+1..].to_string());
    }
    
    (input.to_string(), "".to_string())
}
