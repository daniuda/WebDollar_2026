use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager, State, WindowEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

// Binarul CLI (fără nod complet) rulează ca "sidecar" Tauri — un .exe de sine
// stătător (Node SEA, fără dependență de Node.js instalat pe mașina
// utilizatorului), declarat în tauri.conf.json -> bundle.externalBin și
// aflat în src-tauri/binaries/webd-miner-cli-<target-triple>.exe. Protocolul
// critic (fix de offset + parolă) NU e rescris în Rust — rulăm direct
// scriptul deja validat contra pool-ului live.
const SIDECAR_NAME: &str = "webd-miner-cli";

struct MinerProcess(Mutex<Option<CommandChild>>);

#[tauri::command]
fn start_miner(
    app: tauri::AppHandle,
    state: State<MinerProcess>,
    wallet_path: String,
    pool_url: String,
    pool_public_key_hex: String,
    password: Option<String>,
) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if guard.is_some() {
        return Err("Minerul rulează deja — apasă Stop întâi.".into());
    }

    let mut args = vec![
        wallet_path,
        pool_url,
        pool_public_key_hex,
        "--submit".to_string(),
        "--status-interval=15".to_string(),
    ];
    if let Some(pwd) = password.filter(|p| !p.is_empty()) {
        args.push(format!("--password={}", pwd));
    }

    let (mut rx, child) = app
        .shell()
        .sidecar(SIDECAR_NAME)
        .map_err(|e| format!("Sidecar-ul minerului nu a fost găsit: {e}"))?
        .args(args)
        .spawn()
        .map_err(|e| format!("Nu am putut porni minerul: {e}"))?;

    let app_clone = app.clone();
    tauri::async_runtime::spawn(async move {
        use tauri_plugin_shell::process::CommandEvent;
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    let text = String::from_utf8_lossy(&line).trim_end().to_string();
                    let _ = app_clone.emit("miner-log", text);
                }
                CommandEvent::Terminated(payload) => {
                    let _ = app_clone.emit("miner-exit", payload.code);
                    if let Some(state) = app_clone.try_state::<MinerProcess>() {
                        if let Ok(mut guard) = state.0.lock() {
                            *guard = None;
                        }
                    }
                }
                _ => {}
            }
        }
    });

    *guard = Some(child);
    Ok(())
}

#[tauri::command]
fn stop_miner(app: tauri::AppHandle, state: State<MinerProcess>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(child) = guard.take() {
        let _ = child.kill();
        let _ = app.emit("miner-exit", None::<i32>);
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(MinerProcess(Mutex::new(None)))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let show_hide = MenuItem::with_id(app, "show_hide", "Arată / Ascunde", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Ieșire (oprește și minerul)", true, None::<&str>)?;
            let tray_menu = Menu::with_items(app, &[&show_hide, &quit])?;

            let icon = app.default_window_icon().cloned();
            let mut tray_builder = TrayIconBuilder::new()
                .tooltip("WebDollar Miner")
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show_hide" => toggle_main_window(app),
                    "quit" => {
                        stop_miner_process(app);
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let tauri::tray::TrayIconEvent::Click {
                        button: tauri::tray::MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_main_window(tray.app_handle());
                    }
                });
            if let Some(icon) = icon {
                tray_builder = tray_builder.icon(icon);
            }
            tray_builder.build(app)?;

            // închiderea ferestrei (X) nu termină aplicația — doar o ascunde în
            // tray; minerul continuă să ruleze în fundal. Ieșirea reală se face
            // doar din meniul tray-ului ("Ieșire"), ca să oprim minerul explicit.
            if let Some(window) = app.get_webview_window("main") {
                let window_clone = window.clone();
                window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        api.prevent_close();
                        let _ = window_clone.hide();
                    }
                });
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![start_miner, stop_miner])
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}

fn toggle_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

fn stop_miner_process(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<MinerProcess>() {
        if let Ok(mut guard) = state.0.lock() {
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
    }
}
