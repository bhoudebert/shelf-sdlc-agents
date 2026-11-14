#![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn temp_dir(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("warden-script-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("temp dir");
    dir
}

fn target() -> String {
    let os = match std::env::consts::OS {
        "linux" => "unknown-linux-musl",
        "macos" => "apple-darwin",
        other => panic!("not a system the script supports: {other}"),
    };
    let arch = match std::env::consts::ARCH {
        "x86_64" => "x86_64",
        "aarch64" => "aarch64",
        other => panic!("not an architecture the script supports: {other}"),
    };
    format!("{arch}-{os}")
}

fn script() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("install.sh")
}

/// A fake release: the real binary in a tarball, and a checksums file, in a folder the script reads by URL.
fn release(dir: &Path, corrupt: bool) {
    let staging = dir.join("staging");
    std::fs::create_dir_all(&staging).expect("staging");
    std::fs::copy(env!("CARGO_BIN_EXE_warden"), staging.join("warden")).expect("binary");
    let asset = format!("warden-{}.tar.gz", target());
    let tar = Command::new("tar")
        .args(["-czf"])
        .arg(dir.join(&asset))
        .args(["-C"])
        .arg(&staging)
        .arg("warden")
        .status()
        .expect("tar");
    assert!(tar.success());
    let sum = Command::new("sha256sum")
        .arg(dir.join(&asset))
        .output()
        .or_else(|_| Command::new("shasum").args(["-a", "256"]).arg(dir.join(&asset)).output())
        .expect("a checksum program");
    let hash = String::from_utf8_lossy(&sum.stdout).split_whitespace().next().expect("hash").to_owned();
    let shown = if corrupt { "0".repeat(64) } else { hash };
    std::fs::write(dir.join("checksums.txt"), format!("{shown}  {asset}\n")).expect("checksums");
}

fn install(dir: &Path, install_dir: &Path) -> Output {
    Command::new("sh")
        .arg(script())
        .env("WARDEN_BASE_URL", format!("file://{}", dir.display()))
        .env("WARDEN_INSTALL_DIR", install_dir)
        .env("HOME", dir)
        .output()
        .expect("runs")
}

fn text(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned() + &String::from_utf8_lossy(&output.stderr)
}

#[test]
fn the_script_installs_a_verified_binary_that_runs() {
    let dir = temp_dir("good");
    release(&dir, false);
    let bin = dir.join("bin");
    let output = install(&dir, &bin);
    assert!(output.status.success(), "{}", text(&output));
    let version = Command::new(bin.join("warden")).arg("version").output().expect("runs");
    assert_eq!(String::from_utf8_lossy(&version.stdout), format!("warden {}\n", env!("CARGO_PKG_VERSION")));
    assert!(text(&output).contains("Next: warden init"), "{}", text(&output));
    assert!(text(&output).contains("is not on your PATH"), "{}", text(&output));
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn a_download_that_does_not_match_its_checksum_is_not_installed() {
    let dir = temp_dir("bad");
    release(&dir, true);
    let bin = dir.join("bin");
    let output = install(&dir, &bin);
    assert!(!output.status.success());
    assert!(text(&output).contains("checksum mismatch"), "{}", text(&output));
    assert!(!bin.join("warden").exists());
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn a_release_that_is_not_there_is_reported() {
    let dir = temp_dir("missing");
    let output = install(&dir, &dir.join("bin"));
    assert!(!output.status.success());
    assert!(text(&output).contains("could not download"), "{}", text(&output));
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn the_script_is_valid_posix_shell() {
    let output = Command::new("sh").arg("-n").arg(script()).output().expect("runs");
    assert!(output.status.success(), "{}", text(&output));
}
