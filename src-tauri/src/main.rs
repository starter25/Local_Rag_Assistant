#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use rfd::{MessageDialog, MessageLevel};
use std::{
    env,
    fs::{self, OpenOptions},
    io::Write,
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager, RunEvent};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const APP_LABEL: &str = "main";
const APP_TITLE: &str = "Local RAG Assistant";
const HOST: &str = "127.0.0.1";
const OLLAMA_TAGS_URL: &str = "http://127.0.0.1:11434/api/tags";
const BACKEND_READY_TIMEOUT: Duration = Duration::from_secs(30);
const HEALTHCHECK_TIMEOUT: Duration = Duration::from_secs(2);

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct ServerState(Mutex<Option<Child>>);

struct BackendLayout {
    python_path: PathBuf,
    backend_root: PathBuf,
    storage_root: PathBuf,
    runtime_root: PathBuf,
}

fn main() {
    let builder = tauri::Builder::default()
        .manage(ServerState(Mutex::new(None)))
        .setup(|app| {
            let app_handle = app.handle().clone();
            let (api_url, child) = start_backend(&app_handle)?;

            {
                let state = app.state::<ServerState>();
                let mut guard = state.0.lock().expect("server state lock");
                *guard = Some(child);
            }

            let window = app
                .get_webview_window(APP_LABEL)
                .ok_or_else(|| "Could not find the main application window.".to_string())?;

            let api_url_literal =
                serde_json::to_string(&api_url).map_err(|err| err.to_string())?;
            let init_script = format!(
                "window.__LOCAL_RAG_DESKTOP__ = true; \
                 window.__LOCAL_RAG_API_URL__ = {0}; \
                 window.dispatchEvent(new CustomEvent('local-rag-api-ready', {{ detail: {{ apiBaseUrl: {0} }} }}));",
                api_url_literal
            );

            window.eval(&init_script).map_err(|err| err.to_string())?;
            window.show().map_err(|err| err.to_string())?;
            let _ = window.set_focus();

            if !check_url(OLLAMA_TAGS_URL, HEALTHCHECK_TIMEOUT) {
                show_dialog(
                    MessageLevel::Warning,
                    "Ollama does not appear to be running. Start Ollama before uploading documents or asking questions.",
                );
            }

            Ok(())
        });

    let app = match builder.build(tauri::generate_context!()) {
        Ok(app) => app,
        Err(err) => {
            show_dialog(
                MessageLevel::Error,
                &format!("Local RAG Assistant could not start.\n\n{err}"),
            );
            return;
        }
    };

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            stop_backend(app_handle);
        }
    });
}

fn show_dialog(level: MessageLevel, description: &str) {
    MessageDialog::new()
        .set_level(level)
        .set_title(APP_TITLE)
        .set_description(description)
        .show();
}

fn is_dev() -> bool {
    cfg!(debug_assertions)
}

fn project_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .canonicalize()
        .map_err(|err| format!("Could not resolve the project root: {err}"))
}

fn choose_port() -> Result<u16, String> {
    let listener = TcpListener::bind((HOST, 0))
        .map_err(|err| format!("Could not allocate a local backend port: {err}"))?;
    let port = listener
        .local_addr()
        .map_err(|err| format!("Could not read the local backend address: {err}"))?
        .port();
    drop(listener);
    Ok(port)
}

fn check_url(url: &str, timeout: Duration) -> bool {
    ureq::get(url)
        .timeout(timeout)
        .call()
        .map(|response| response.status() < 500)
        .unwrap_or(false)
}

fn wait_for_ready(api_url: &str, timeout: Duration) -> bool {
    let ready_url = format!("{api_url}/ready");
    let started = Instant::now();

    while started.elapsed() < timeout {
        if check_url(&ready_url, HEALTHCHECK_TIMEOUT) {
            return true;
        }

        thread::sleep(Duration::from_millis(500));
    }

    false
}

fn open_log_file(path: &Path) -> Result<Stdio, String> {
    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|err| format!("Could not open the log file ({}): {err}", path.display()))?;

    Ok(Stdio::from(file))
}

fn append_text_log(path: &Path, message: &str) {
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{message}");
    }
}

fn log_dir_for_storage(storage_root: &Path) -> Result<PathBuf, String> {
    fs::create_dir_all(storage_root)
        .map_err(|err| format!("Could not create the storage directory: {err}"))?;

    let log_dir = storage_root.join("logs");
    fs::create_dir_all(&log_dir)
        .map_err(|err| format!("Could not create the log directory: {err}"))?;

    Ok(log_dir)
}

fn dev_backend_layout() -> Result<BackendLayout, String> {
    let root = project_root()?;
    Ok(BackendLayout {
        python_path: root.join("venv").join("Scripts").join("python.exe"),
        backend_root: root.clone(),
        storage_root: root.join("storage"),
        runtime_root: root,
    })
}

fn push_candidate(candidates: &mut Vec<PathBuf>, candidate: PathBuf) {
    if !candidates.iter().any(|existing| existing == &candidate) {
        candidates.push(candidate);
    }
}

fn bundled_backend_layout(app: &AppHandle) -> Result<BackendLayout, String> {
    let storage_root = app
        .path()
        .app_local_data_dir()
        .map_err(|err| format!("Could not resolve the application data directory: {err}"))?
        .join("storage");

    let mut candidate_roots = Vec::new();

    if let Ok(resource_dir) = app.path().resource_dir() {
        push_candidate(&mut candidate_roots, resource_dir.clone());
        push_candidate(
            &mut candidate_roots,
            resource_dir.join("desktop-runtime"),
        );
        push_candidate(
            &mut candidate_roots,
            resource_dir.join("_up_").join("desktop-runtime"),
        );
    }

    if let Ok(current_exe) = env::current_exe() {
        if let Some(exe_dir) = current_exe.parent() {
            push_candidate(&mut candidate_roots, exe_dir.to_path_buf());
            push_candidate(&mut candidate_roots, exe_dir.join("desktop-runtime"));
            push_candidate(
                &mut candidate_roots,
                exe_dir.join("_up_").join("desktop-runtime"),
            );

            if let Some(parent_dir) = exe_dir.parent() {
                push_candidate(
                    &mut candidate_roots,
                    parent_dir.join("_up_").join("desktop-runtime"),
                );
            }
        }
    }

    let mut tried_locations = Vec::new();

    for runtime_root in candidate_roots {
        let python_path = runtime_root.join("python").join("python.exe");
        let backend_root = runtime_root.join("backend");
        let backend_entry = backend_root.join("app").join("main.py");

        tried_locations.push(format!(
            "python={} | backend={}",
            python_path.display(),
            backend_entry.display()
        ));

        if python_path.exists() && backend_entry.exists() {
            return Ok(BackendLayout {
                python_path,
                backend_root,
                storage_root,
                runtime_root,
            });
        }
    }

    Err(format!(
        "Could not locate the bundled backend runtime.\nTried:\n{}",
        tried_locations.join("\n")
    ))
}

fn start_backend(app: &AppHandle) -> Result<(String, Child), String> {
    let port = choose_port()?;
    let api_url = format!("http://{HOST}:{port}");
    let layout = if is_dev() {
        dev_backend_layout()?
    } else {
        bundled_backend_layout(app)?
    };

    let log_dir = log_dir_for_storage(&layout.storage_root)?;
    let launcher_log = log_dir.join("desktop-launcher.log");
    append_text_log(
        &launcher_log,
        &format!(
            "mode={} runtime_root={} python={} backend={} api_url={}",
            if is_dev() { "dev" } else { "bundle" },
            layout.runtime_root.display(),
            layout.python_path.display(),
            layout.backend_root.display(),
            api_url
        ),
    );

    if !layout.python_path.exists() {
        let message = format!(
            "Could not find the Python executable.\n{}\n\nSee: {}",
            layout.python_path.display(),
            launcher_log.display()
        );
        append_text_log(&launcher_log, &message);
        return Err(message);
    }

    if !layout.backend_root.join("app").join("main.py").exists() {
        let message = format!(
            "The backend runtime is missing the FastAPI entrypoint.\n{}\n\nSee: {}",
            layout.backend_root.display(),
            launcher_log.display()
        );
        append_text_log(&launcher_log, &message);
        return Err(message);
    }

    let stdout_log = log_dir.join("desktop-server.stdout.log");
    let stderr_log = log_dir.join("desktop-server.stderr.log");
    let stdout = open_log_file(&stdout_log)?;
    let stderr = open_log_file(&stderr_log)?;

    let mut command = Command::new(&layout.python_path);
    command
        .arg("-m")
        .arg("app.desktop_server")
        .current_dir(&layout.backend_root)
        .env("LOCAL_RAG_BASE_DIR", &layout.backend_root)
        .env("LOCAL_RAG_STORAGE_DIR", &layout.storage_root)
        .env("LOCAL_RAG_ENABLE_STATIC_FRONTEND", "0")
        .env("LOCAL_RAG_SERVER_HOST", HOST)
        .env("LOCAL_RAG_SERVER_PORT", port.to_string())
        .stdout(stdout)
        .stderr(stderr);

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    let mut child = command.spawn().map_err(|err| {
        let message = format!(
            "The bundled Python backend could not be started: {err}\n\nSee: {}",
            launcher_log.display()
        );
        append_text_log(&launcher_log, &message);
        message
    })?;

    if wait_for_ready(&api_url, BACKEND_READY_TIMEOUT) {
        append_text_log(&launcher_log, "Backend ready.");
        return Ok((api_url, child));
    }

    let _ = child.kill();
    let _ = child.wait();

    let message = format!(
        "The bundled backend did not become ready within {} seconds.\n\nLogs:\n{}\n{}",
        BACKEND_READY_TIMEOUT.as_secs(),
        stdout_log.display(),
        stderr_log.display()
    );
    append_text_log(&launcher_log, &message);

    Err(message)
}

fn stop_backend(app: &AppHandle) {
    let child = {
        let state = app.state::<ServerState>();
        let mut guard = match state.0.lock() {
            Ok(guard) => guard,
            Err(_) => return,
        };

        guard.take()
    };

    if let Some(mut child) = child {
        let _ = child.kill();
        let _ = child.wait();
    }
}
