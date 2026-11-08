# AProgram Rust and GPUI Implementation Plan

> Execute in order at integration points. Independent persistence, process and tray modules can be developed concurrently.

**Goal:** Run AProgram as a Windows x64 Rust application with direct environment switching from its tray menu and a reusable GPUI window.

**Architecture:** One GPUI application owns the window and shared model. Win32 tray commands enter the same model through an event channel. A background task handles Windows process work and reports outcomes to the model.

**Tech stack:** Rust 2024, GPUI 0.2.2 with Windows manifest, Win32, Serde, and Cargo.

## Milestones

- [x] Create the Cargo package and validate GPUI startup, window handle and Windows build tooling. Use a real Windows desktop window as the smoke test.
- [x] Add a Win32 tray icon and native group menu in `src/tray.rs`. Test single instance and event dispatch. Verify hide and restore reuse the same HWND.
- [x] Implement `src/state.rs` with atomic state writes and read-only legacy import. Test path-only, structured, mixed, relative and invalid inputs, plus a save/load round trip.
- [x] Implement `src/process.rs` with differential planning, complete path matching, background Windows Shell launches, graceful close, shared timeout and confirmed force close. Test common applications, already-running targets and retries. Exercise launch and close against disposable fixture executables.
- [x] Integrate `src/main.rs`, `src/ui.rs` and `src/platform.rs`. Exercise the desktop window, group creation, native tray commands, status refresh and window recovery. Confirm hidden state cancels the refresh task.
- [x] Run `cargo fmt --check`, `cargo test --release --locked`, `cargo clippy --release --locked --all-targets -- -D warnings` and `cargo build --release --locked`. Run the native smoke and performance comparison on Windows 11 with 20 fixture entries. Record dispatch and restore latency, scan count, CPU time, working set and private commit.

## Windows verification

- Release build, formatting and Clippy passed. Eleven tests passed. The test executable's subprocess fixture is marked ignored and invoked by the Windows integration test. The integration test covers shortcut arguments, wrong-path isolation, retargeted shortcuts, graceful close, shared timeout and explicit force close.
- Thirty tray restores reused the same PID and HWND. The p95 from posting the tray restore message to observing the visible window's frame callback was 34.0 ms. The harness also checked that the restored window responded to a Win32 message.
- Thirty actual switch commands launched the expected alternating test executables. With 19 common entries and one distinct entry per group, p95 from command handling to the first Windows launch request was 27.3 ms. Five accessibility invocations were replayed after timing out before the command reached the app. Their timings are excluded from the 30 commands.

| Hidden idle with 20 entries | Python, one 60 s run | Rust + GPUI, three 60 s runs |
| --- | ---: | ---: |
| CPU time per second | 66.4 ms | 6.0–7.6 ms |
| Periodic scans per run | 600 | 0 |
| Working set | 68.4 MiB | 92.8–95.6 MiB |
| Private commit | 40.1 MiB | 97.7–97.9 MiB |

The long runs and window restore used the build before a follow-up Shell COM initialization fix. The real-launch measurement used the final Release build. One visible idle GPU counter sample showed 0% engine utilization and 31.2 MiB shared GPU memory. It does not establish GPU utilization over the full run.
