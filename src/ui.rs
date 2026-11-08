use gpui::{
    ClickEvent, Context, Div, ExternalPaths, Stateful, Window, div, img, prelude::*, px, rgb,
};

use crate::{Launcher, NameAction, process::Command};

const BACKGROUND: u32 = 0xf8f9fb;
const SIDEBAR: u32 = 0xf0f3f7;
const WHITE: u32 = 0xffffff;
const TEXT: u32 = 0x1c2533;
const MUTED: u32 = 0x556479;
const LINE: u32 = 0xdce3ec;
const ACCENT: u32 = 0x2056bf;
const SELECTED: u32 = 0xdfeaff;
const GREEN: u32 = 0x16724c;

impl Render for Launcher {
    fn render(&mut self, _: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let sidebar = self.render_sidebar(cx);
        let content = self.render_content(cx);
        div()
            .size_full()
            .flex()
            .bg(rgb(BACKGROUND))
            .text_color(rgb(TEXT))
            .text_size(px(14.))
            .child(sidebar)
            .child(content)
    }
}

impl Launcher {
    fn render_sidebar(&self, cx: &Context<Self>) -> Div {
        let groups = self.state.groups.iter().enumerate().map(|(index, group)| {
            let name = group.name.clone();
            let current = self
                .state
                .active
                .as_ref()
                .is_some_and(|active| active.group == name);
            let selected = self.state.selected.as_ref() == Some(&name);
            div()
                .id(("group", index))
                .flex()
                .items_center()
                .justify_between()
                .gap_2()
                .px_3()
                .py_2()
                .rounded_md()
                .cursor_pointer()
                .when(selected, |row| {
                    row.bg(rgb(SELECTED)).text_color(rgb(ACCENT))
                })
                .hover(|row| row.bg(rgb(SELECTED)))
                .child(
                    div()
                        .min_w_0()
                        .overflow_hidden()
                        .text_ellipsis()
                        .child(name.clone()),
                )
                .when(current, |row| {
                    row.child(
                        div()
                            .flex_none()
                            .text_size(px(11.))
                            .text_color(rgb(GREEN))
                            .child("当前"),
                    )
                })
                .on_click(cx.listener(move |this, _, window, cx| {
                    this.finish_pending_click(cx);
                    this.state.selected = Some(name.clone());
                    this.persist();
                    this.refresh_status(window, cx);
                    cx.notify();
                }))
        });
        div()
            .w(px(212.))
            .flex_none()
            .flex()
            .flex_col()
            .gap_3()
            .p_4()
            .border_r_1()
            .border_color(rgb(LINE))
            .bg(rgb(SIDEBAR))
            .child(
                div()
                    .flex()
                    .items_center()
                    .justify_between()
                    .child(
                        div()
                            .text_size(px(16.))
                            .font_weight(gpui::FontWeight::SEMIBOLD)
                            .child("软件组"),
                    )
                    .child(button("new", "＋ 新建", false, false).on_click(cx.listener(
                        |this, _, window, cx| {
                            this.edit_name(NameAction::New, window, cx);
                        },
                    ))),
            )
            .child(
                div()
                    .id("groups")
                    .flex_1()
                    .min_h_0()
                    .overflow_y_scroll()
                    .flex()
                    .flex_col()
                    .gap_1()
                    .children(groups),
            )
            .child(
                button("settings", "设置与导入", self.settings_open, false).on_click(cx.listener(
                    |this, _, _, cx| {
                        this.settings_open = !this.settings_open;
                        cx.notify();
                    },
                )),
            )
    }

    fn render_content(&self, cx: &Context<Self>) -> Stateful<Div> {
        let content = match self.selected() {
            Some(group) => {
                let name = group.name.clone();
                let to_switch = name.clone();
                let to_launch = group.clone();
                let to_close = group.clone();
                let to_rename = name.clone();
                let to_copy = name.clone();
                let to_delete = name.clone();
                let cards = group.apps.iter().enumerate().map(|(index, app)| {
                    let path = app.path.clone();
                    let to_remove = path.clone();
                    let name = path
                        .file_stem()
                        .unwrap_or(path.as_os_str())
                        .to_string_lossy()
                        .into_owned();
                    let running = self.running.contains(&path);
                    let icon = self.icons.get(&path).and_then(|entry| entry.clone());
                    let app_icon = div()
                        .flex_none()
                        .size(px(38.))
                        .rounded_md()
                        .bg(rgb(SIDEBAR))
                        .flex()
                        .items_center()
                        .justify_center()
                        .when_some(icon, |element, icon| element.child(img(icon).size(px(24.))));
                    div()
                        .id(("app", index))
                        .flex()
                        .items_center()
                        .gap_3()
                        .px_3()
                        .py_2()
                        .rounded_md()
                        .border_1()
                        .border_color(rgb(LINE))
                        .bg(rgb(WHITE))
                        .cursor_pointer()
                        .hover(|element| element.border_color(rgb(ACCENT)))
                        .child(app_icon)
                        .child(
                            div()
                                .flex_1()
                                .min_w_0()
                                .flex()
                                .flex_col()
                                .gap_1()
                                .child(div().overflow_hidden().text_ellipsis().child(name))
                                .child(
                                    div()
                                        .text_size(px(12.))
                                        .text_color(rgb(if running { GREEN } else { MUTED }))
                                        .child(if running { "运行中" } else { "未运行" }),
                                ),
                        )
                        .child(
                            div()
                                .flex_none()
                                .text_size(px(12.))
                                .text_color(rgb(if app.enabled { ACCENT } else { MUTED }))
                                .child(if app.enabled {
                                    "已启用"
                                } else {
                                    "已停用"
                                }),
                        )
                        .child(button("remove", "移除", false, false).on_click(cx.listener(
                            move |this, _, window, cx| {
                                cx.stop_propagation();
                                this.finish_pending_click(cx);
                                this.remove_app(&to_remove, window, cx);
                            },
                        )))
                        .on_click(cx.listener(move |this, event: &ClickEvent, window, cx| {
                            this.app_click(&path, event.click_count(), window, cx);
                        }))
                });
                div()
                    .size_full()
                    .flex()
                    .flex_col()
                    .gap_4()
                    .child(
                        div()
                            .flex()
                            .items_center()
                            .justify_between()
                            .gap_3()
                            .child(
                                div()
                                    .min_w_0()
                                    .overflow_hidden()
                                    .text_ellipsis()
                                    .text_size(px(24.))
                                    .font_weight(gpui::FontWeight::SEMIBOLD)
                                    .child(name),
                            )
                            .child(
                                div()
                                    .flex_none()
                                    .flex()
                                    .items_center()
                                    .gap_2()
                                    .child(button("close", "关闭组", false, self.busy).on_click(
                                        cx.listener(move |this, _, window, cx| {
                                            if !this.busy {
                                                this.confirm_command(
                                                    Command::Close(to_close.clone()),
                                                    window,
                                                    cx,
                                                );
                                            }
                                        }),
                                    ))
                                    .child(button("launch", "启动组", false, self.busy).on_click(
                                        cx.listener(move |this, _, window, cx| {
                                            this.run(
                                                Command::Launch(to_launch.clone()),
                                                "正在启动软件组…".into(),
                                                Some(window),
                                                cx,
                                            );
                                        }),
                                    ))
                                    .child(
                                        button("switch", "切换到此组", true, self.busy).on_click(
                                            cx.listener(move |this, _, window, cx| {
                                                this.switch(&to_switch, Some(window), cx);
                                            }),
                                        ),
                                    ),
                            ),
                    )
                    .child(
                        div()
                            .flex()
                            .flex_wrap()
                            .gap_2()
                            .child(button("add-app", "＋ 添加应用", false, false).on_click(
                                cx.listener(|this, _, window, cx| this.select_paths(window, cx)),
                            ))
                            .child(button("rename", "重命名", false, self.busy).on_click(
                                cx.listener(move |this, _, window, cx| {
                                    if !this.busy {
                                        this.edit_name(
                                            NameAction::Rename(to_rename.clone()),
                                            window,
                                            cx,
                                        );
                                    }
                                }),
                            ))
                            .child(button("copy", "复制组", false, self.busy).on_click(
                                cx.listener(move |this, _, window, cx| {
                                    if !this.busy {
                                        this.edit_name(
                                            NameAction::Copy(to_copy.clone()),
                                            window,
                                            cx,
                                        );
                                    }
                                }),
                            ))
                            .child(button("delete", "删除组", false, self.busy).on_click(
                                cx.listener(move |this, _, window, cx| {
                                    if !this.busy {
                                        this.delete_group(to_delete.clone(), window, cx);
                                    }
                                }),
                            )),
                    )
                    .child(
                        div()
                            .id("apps")
                            .flex_1()
                            .min_h_0()
                            .overflow_y_scroll()
                            .flex()
                            .flex_col()
                            .gap_2()
                            .when(group.apps.is_empty(), |element| {
                                element.child(
                                    div()
                                        .w_full()
                                        .p_6()
                                        .border_1()
                                        .border_dashed()
                                        .border_color(rgb(LINE))
                                        .rounded_md()
                                        .text_color(rgb(MUTED))
                                        .child("拖入 EXE 或快捷方式来添加应用。"),
                                )
                            })
                            .children(cards),
                    )
            }
            None => div()
                .flex_1()
                .flex()
                .flex_col()
                .items_center()
                .justify_center()
                .gap_3()
                .child(
                    div()
                        .text_size(px(24.))
                        .font_weight(gpui::FontWeight::SEMIBOLD)
                        .child("添加你的第一个软件组"),
                )
                .child(
                    div()
                        .text_color(rgb(MUTED))
                        .child("把办公、游戏等场景需要的应用放在一起。"),
                )
                .child(
                    div()
                        .flex()
                        .gap_2()
                        .child(button("empty-new", "新建软件组", true, false).on_click(
                            cx.listener(|this, _, window, cx| {
                                this.edit_name(NameAction::New, window, cx)
                            }),
                        ))
                        .child(
                            button("empty-import", "导入旧版配置", false, self.busy).on_click(
                                cx.listener(|this, _, window, cx| {
                                    if !this.busy {
                                        this.import(this.legacy_dir.clone(), window, cx);
                                    }
                                }),
                            ),
                        ),
                ),
        };
        div()
            .id("content")
            .flex_1()
            .min_w_0()
            .flex()
            .flex_col()
            .gap_3()
            .p_5()
            .on_drop(cx.listener(|this, paths: &ExternalPaths, window, cx| {
                this.add_paths(paths.paths(), window, cx)
            }))
            .when(self.settings_open, |element| {
                element.child(self.render_settings(cx))
            })
            .when_some(self.load_error.clone(), |element, error| {
                element.child(
                    div()
                        .p_3()
                        .rounded_md()
                        .bg(rgb(0xffefe1))
                        .text_color(rgb(0x7a3d13))
                        .flex()
                        .items_center()
                        .gap_3()
                        .child(div().flex_1().min_w_0().child(error))
                        .child(button("recover", "备份并保存", false, false).on_click(
                            cx.listener(|this, _, window, cx| {
                                this.recover(window, cx);
                            }),
                        )),
                )
            })
            .child(div().flex_1().min_h_0().flex().flex_col().child(content))
            .when(!self.status.is_empty(), |element| {
                element.child(self.render_status(cx))
            })
    }

    fn render_settings(&self, cx: &Context<Self>) -> Div {
        let auto_start = match (self.state.settings.auto_start, self.auto_start_pending) {
            (_, true) => "应用导入的开机启动设置",
            (true, false) => "开机自启 · 已开启",
            (false, false) => "开机自启 · 已关闭",
        };
        div()
            .flex()
            .flex_wrap()
            .items_center()
            .gap_2()
            .p_3()
            .bg(rgb(SIDEBAR))
            .rounded_md()
            .child(
                button(
                    "autostart",
                    auto_start,
                    self.state.settings.auto_start && !self.auto_start_pending,
                    false,
                )
                .on_click(cx.listener(|this, _, _, cx| this.toggle_auto_start(cx))),
            )
            .child(
                button(
                    "tray-option",
                    if self.state.settings.minimize_to_tray {
                        "关闭时收到托盘 · 开启"
                    } else {
                        "关闭时收到托盘 · 关闭"
                    },
                    false,
                    false,
                )
                .on_click(cx.listener(|this, _, _, cx| {
                    this.state.settings.minimize_to_tray = !this.state.settings.minimize_to_tray;
                    this.persist();
                    cx.notify();
                })),
            )
            .child(
                button("legacy-picker", "导入旧版目录", false, self.busy).on_click(cx.listener(
                    |this, _, window, cx| {
                        if !this.busy {
                            this.import(None, window, cx);
                        }
                    },
                )),
            )
    }

    fn render_status(&self, cx: &Context<Self>) -> Div {
        div()
            .flex_none()
            .flex()
            .items_start()
            .gap_3()
            .border_t_1()
            .border_color(rgb(LINE))
            .pt_2()
            .child(
                div()
                    .flex_1()
                    .min_w_0()
                    .text_size(px(13.))
                    .text_color(rgb(MUTED))
                    .child(self.status.clone())
                    .when(!self.failures.is_empty(), |element| {
                        element.child(
                            div()
                                .id("failures")
                                .max_h(px(100.))
                                .overflow_y_scroll()
                                .children(
                                    self.failures
                                        .iter()
                                        .map(|message| div().child(message.clone())),
                                ),
                        )
                    }),
            )
            .when(!self.forceable.is_empty(), |element| {
                element.child(
                    button("force-close", "强制结束…", false, self.busy).on_click(cx.listener(
                        |this, _, window, cx| {
                            this.confirm_command(
                                Command::Force(this.forceable.clone()),
                                window,
                                cx,
                            );
                        },
                    )),
                )
            })
    }
}

fn button(id: &'static str, label: &str, primary: bool, disabled: bool) -> Stateful<Div> {
    let (background, color) = match (primary, disabled) {
        (_, true) => (SIDEBAR, MUTED),
        (true, false) => (ACCENT, WHITE),
        (false, false) => (WHITE, TEXT),
    };
    div()
        .id(id)
        .flex_none()
        .px_3()
        .py_1()
        .rounded_md()
        .border_1()
        .border_color(rgb(if primary && !disabled { ACCENT } else { LINE }))
        .bg(rgb(background))
        .text_color(rgb(color))
        .child(label.to_owned())
        .when(!disabled, |element| {
            element
                .cursor_pointer()
                .hover(|style| style.bg(rgb(if primary { 0x194aa8 } else { SELECTED })))
        })
}
