use std::{
    env, fs,
    io::{ErrorKind, Write},
    path::{self, Path, PathBuf},
};

use anyhow::{Context as _, Result, ensure};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Map, Value};
use tempfile::NamedTempFile;

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
pub struct State {
    pub groups: Vec<Group>,
    pub settings: Settings,
    pub active: Option<Applied>,
    pub selected: Option<String>,
    pub window: Option<WindowState>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Group {
    pub name: String,
    pub apps: Vec<AppEntry>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct AppEntry {
    pub path: PathBuf,
    pub enabled: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(default)]
pub struct Settings {
    pub auto_start: bool,
    pub minimize_to_tray: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            auto_start: false,
            minimize_to_tray: true,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Applied {
    pub group: String,
    pub enabled: Vec<PathBuf>,
    pub failed_open: Vec<PathBuf>,
    pub failed_close: Vec<PathBuf>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct WindowState {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

pub fn state_path() -> Result<PathBuf> {
    let local_app_data = env::var_os("LOCALAPPDATA")
        .filter(|path| !path.is_empty())
        .context("LOCALAPPDATA is unavailable")?;
    Ok(PathBuf::from(local_app_data)
        .join("AProgram")
        .join("state.json"))
}

pub fn load(path: &Path) -> Result<State> {
    load_or_default(path)
}

fn load_or_default<T: Default + DeserializeOwned>(path: &Path) -> Result<T> {
    match fs::read(path) {
        Ok(data) => parse_object(&data, path),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(T::default()),
        Err(error) => Err(error).with_context(|| format!("Could not read {}", path.display())),
    }
}

fn parse_object<T: DeserializeOwned>(data: &[u8], path: &Path) -> Result<T> {
    ensure!(
        data.trim_ascii_start().starts_with(b"{"),
        "Expected a JSON object in {}",
        path.display()
    );
    serde_json::from_slice(data)
        .with_context(|| format!("Invalid configuration in {}", path.display()))
}

pub fn save(path: &Path, state: &State) -> Result<()> {
    let data = serde_json::to_vec_pretty(state).context("Could not encode launcher state")?;
    let dir = path
        .parent()
        .filter(|dir| !dir.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(dir).with_context(|| format!("Could not create {}", dir.display()))?;

    let mut temporary = NamedTempFile::new_in(dir)
        .with_context(|| format!("Could not create a temporary file in {}", dir.display()))?;
    let file = temporary.as_file_mut();
    file.write_all(&data)
        .and_then(|()| file.sync_all())
        .with_context(|| format!("Could not write launcher state in {}", dir.display()))?;
    temporary
        .persist(path)
        .map_err(|error| error.error)
        .with_context(|| format!("Could not replace {}", path.display()))?;
    Ok(())
}

#[derive(Deserialize)]
#[serde(untagged)]
enum LegacyApp {
    Path(PathBuf),
    Entry {
        path: PathBuf,
        #[serde(default = "default_enabled")]
        enabled: bool,
    },
}

fn default_enabled() -> bool {
    true
}

pub fn import_legacy(dir: &Path) -> Result<State> {
    let dir = path::absolute(dir)
        .with_context(|| format!("Could not resolve legacy directory {}", dir.display()))?;
    let groups_path = dir.join("software_groups.json");
    let data = fs::read(&groups_path)
        .with_context(|| format!("Could not read {}", groups_path.display()))?;
    let legacy_groups: Map<String, Value> = parse_object(&data, &groups_path)?;
    let mut groups = Vec::with_capacity(legacy_groups.len());
    for (name, entries) in legacy_groups {
        let entries: Vec<LegacyApp> = serde_json::from_value(entries)
            .with_context(|| format!("Invalid group {name:?} in {}", groups_path.display()))?;
        let apps = entries
            .into_iter()
            .map(|entry| {
                let (path, enabled) = match entry {
                    LegacyApp::Path(path) => (path, true),
                    LegacyApp::Entry { path, enabled } => (path, enabled),
                };
                AppEntry {
                    path: dir.join(path),
                    enabled,
                }
            })
            .collect();
        groups.push(Group { name, apps });
    }

    Ok(State {
        groups,
        settings: load_or_default(&dir.join("settings.json"))?,
        ..State::default()
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{env, fs};

    #[test]
    fn state_file_lives_under_local_app_data() {
        if let Some(local_app_data) = env::var_os("LOCALAPPDATA").filter(|path| !path.is_empty()) {
            assert_eq!(
                state_path().unwrap(),
                PathBuf::from(local_app_data)
                    .join("AProgram")
                    .join("state.json")
            );
        } else {
            assert!(state_path().is_err());
        }
    }

    #[test]
    fn missing_state_uses_legacy_preference_defaults() {
        let dir = tempfile::tempdir().unwrap();
        let state = load(&dir.path().join("state.json")).unwrap();
        assert!(state.groups.is_empty());
        assert!(!state.settings.auto_start);
        assert!(state.settings.minimize_to_tray);
    }

    #[test]
    fn invalid_state_is_reported_and_preserved() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("state.json");
        for contents in [
            "{",
            "{}",
            r#"{"groups":"invalid","settings":{}}"#,
            r#"[[],{},null,null,null]"#,
        ] {
            fs::write(&path, contents).unwrap();
            assert!(load(&path).is_err(), "accepted invalid state: {contents}");
            assert_eq!(fs::read_to_string(&path).unwrap(), contents);
        }
    }

    #[test]
    fn save_round_trips_state_and_replaces_the_previous_snapshot() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("AProgram").join("state.json");
        let app = dir.path().join("应用.exe");
        let state = State {
            groups: vec![Group {
                name: "办公".into(),
                apps: vec![AppEntry {
                    path: app.clone(),
                    enabled: false,
                }],
            }],
            settings: Settings {
                auto_start: true,
                minimize_to_tray: false,
            },
            active: Some(Applied {
                group: "办公".into(),
                enabled: vec![app.clone()],
                failed_open: vec![app],
                failed_close: vec![dir.path().join("待关闭.exe")],
            }),
            selected: Some("办公".into()),
            window: Some(WindowState {
                x: -200.0,
                y: 90.5,
                width: 850.0,
                height: 540.0,
            }),
        };

        save(&path, &state).unwrap();
        assert_eq!(load(&path).unwrap(), state);

        let replacement = State::default();
        save(&path, &replacement).unwrap();
        assert_eq!(load(&path).unwrap(), replacement);
        assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 1);
    }

    #[cfg(windows)]
    #[test]
    fn failed_save_preserves_the_previous_snapshot() {
        use std::{ffi::OsString, os::windows::ffi::OsStringExt};

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("state.json");
        save(&path, &State::default()).unwrap();
        let original = fs::read(&path).unwrap();
        let invalid_path = PathBuf::from(OsString::from_wide(&[0xd800]));
        let invalid = State {
            groups: vec![Group {
                name: "办公".into(),
                apps: vec![AppEntry {
                    path: invalid_path,
                    enabled: true,
                }],
            }],
            ..State::default()
        };

        assert!(save(&path, &invalid).is_err());
        assert_eq!(fs::read(&path).unwrap(), original);
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[test]
    fn legacy_import_keeps_order_resolves_relative_paths_and_preserves_original_files() {
        let dir = tempfile::tempdir().unwrap();
        let absolute = dir.path().join("绝对路径.exe");
        let absolute_json = serde_json::to_string(&absolute).unwrap();
        let groups = format!(
            r#"{{
                "游戏": ["目录/game.lnk", {{"path": {absolute_json}, "enabled": false}}],
                "办公": [{{"path": "work.exe"}}],
                "空组": []
            }}"#
        );
        let settings = r#"{"auto_start":true,"minimize_to_tray":false}"#;
        let groups_path = dir.path().join("software_groups.json");
        let settings_path = dir.path().join("settings.json");
        fs::write(&groups_path, &groups).unwrap();
        fs::write(&settings_path, settings).unwrap();

        let imported = import_legacy(dir.path()).unwrap();

        assert_eq!(
            imported.groups,
            vec![
                Group {
                    name: "游戏".into(),
                    apps: vec![
                        AppEntry {
                            path: dir.path().join("目录/game.lnk"),
                            enabled: true,
                        },
                        AppEntry {
                            path: absolute,
                            enabled: false,
                        },
                    ],
                },
                Group {
                    name: "办公".into(),
                    apps: vec![AppEntry {
                        path: dir.path().join("work.exe"),
                        enabled: true,
                    }],
                },
                Group {
                    name: "空组".into(),
                    apps: vec![],
                },
            ]
        );
        assert_eq!(
            imported.settings,
            Settings {
                auto_start: true,
                minimize_to_tray: false,
            }
        );
        assert_eq!(fs::read_to_string(&groups_path).unwrap(), groups);
        assert_eq!(fs::read_to_string(&settings_path).unwrap(), settings);
    }

    #[test]
    fn legacy_import_uses_defaults_for_missing_preferences() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("software_groups.json"), "{}").unwrap();
        assert!(import_legacy(dir.path()).unwrap().settings.minimize_to_tray);

        fs::write(dir.path().join("settings.json"), r#"{"auto_start":true}"#).unwrap();
        let settings = import_legacy(dir.path()).unwrap().settings;
        assert!(settings.auto_start);
        assert!(settings.minimize_to_tray);
    }

    #[test]
    fn legacy_import_reports_invalid_source_files() {
        let dir = tempfile::tempdir().unwrap();
        let groups_path = dir.path().join("software_groups.json");
        assert!(import_legacy(dir.path()).is_err());

        for contents in ["null", r#"{"办公":[{"enabled":false}]}"#] {
            fs::write(&groups_path, contents).unwrap();
            assert!(
                import_legacy(dir.path()).is_err(),
                "accepted invalid groups: {contents}"
            );
        }

        fs::write(&groups_path, "{}").unwrap();
        for contents in ["{", "[]"] {
            fs::write(dir.path().join("settings.json"), contents).unwrap();
            assert!(
                import_legacy(dir.path()).is_err(),
                "accepted invalid settings: {contents}"
            );
        }
    }
}
