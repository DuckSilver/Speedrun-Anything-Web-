import flet as ft
import json
import os
import time
import asyncio
from datetime import datetime

DATA_FILE = "../server_speedrun_data.json"

# ==========================================
# 1. THE GLOBAL BRAIN (MULTIPLAYER STATE)
# ==========================================
# This dictionary lives on the server and is shared by ALL connected users.
global_app_data = {}


def load_server_data():
    global global_app_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                global_app_data = json.load(f)
        except Exception:
            global_app_data = {}

    # Migration Engine
    for list_name, content in list(global_app_data.items()):
        if isinstance(content, list):
            global_app_data[list_name] = {"categories": {"General Tasks": content},
                                          "leaderboards": {"timer": [], "clock": []}, "pinned": False}
        elif isinstance(content, dict) and "categories" not in content:
            global_app_data[list_name] = {"categories": content, "leaderboards": {"timer": [], "clock": []},
                                          "pinned": False}

        if "pinned" not in global_app_data[list_name]:
            global_app_data[list_name]["pinned"] = False

        for cat, tasks in global_app_data[list_name]["categories"].items():
            for t in tasks:
                if "weight" not in t: t["weight"] = 1.0
                if "time_type" not in t: t["time_type"] = "duration"
                if "date" not in t: t["date"] = ""

        for mode in ["timer", "clock"]:
            for entry in global_app_data[list_name]["leaderboards"][mode]:
                if "task_times" not in entry:
                    entry["task_times"] = {}


def save_server_data():
    global global_app_data
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(global_app_data, f)
    except Exception:
        pass


# Load the master data once when the server boots up
load_server_data()


# --- TIME PARSING HELPERS ---
def parse_duration(time_str):
    if not time_str: return None
    try:
        parts = [int(p) for p in time_str.strip().split(":")]
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2: return parts[0] * 60 + parts[1]
        return parts[0]
    except:
        return None


def parse_clock(time_str):
    if not time_str: return None
    try:
        return datetime.strptime(time_str.strip().upper(), "%I:%M %p").time()
    except:
        try:
            return datetime.strptime(time_str.strip(), "%H:%M").time()
        except:
            return None


def main(page: ft.Page):
    page.title = "Collaborative Speedrun"
    page.window.width = 400
    page.window.height = 700

    # ==========================================
    # 2. THE WHISPER NETWORK (PUBSUB)
    # ==========================================
    # This listens for any changes made by ANY user on the server
    def on_broadcast(message):
        current_view = getattr(page, "current_view", None)

        if current_view == "main":
            show_main_page(is_sync=True)
        elif current_view and current_view.startswith("list:"):
            target_list = current_view.split(":", 1)[1]
            if target_list in global_app_data:
                show_list_mode(target_list, is_sync=True)
        elif current_view and current_view.startswith("speedrun:"):
            target_list = current_view.split(":", 1)[1]
            if target_list in global_app_data:
                page.update()

    page.pubsub.subscribe(on_broadcast)

    def trigger_global_sync():
        save_server_data()
        page.pubsub.send_all("sync_request")

    def calculate_progress(categories):
        total_weight = 0.0
        completed_weight = 0.0
        for tasks in categories.values():
            for t in tasks:
                w = float(t.get("weight", 1.0))
                total_weight += w
                if t.get("done", False):
                    completed_weight += w
        return completed_weight / total_weight if total_weight > 0 else 0.0

    # ==========================================
    # 3. MAIN PAGE VIEW
    # ==========================================
    def show_main_page(is_sync=False):
        page.current_view = "main"
        page.controls.clear()

        header = ft.Text("Shared Checklists", size=30, weight=ft.FontWeight.BOLD)
        new_list_input = ft.TextField(hint_text="Name a new list...", expand=True)

        def add_list_clicked(e):
            name = new_list_input.value.strip()
            if name and name not in global_app_data:
                global_app_data[name] = {
                    "categories": {},
                    "leaderboards": {"timer": [], "clock": []},
                    "pinned": False
                }
                trigger_global_sync()

        add_btn = ft.ElevatedButton("Create", on_click=add_list_clicked)
        lists_view = ft.ListView(expand=True, spacing=5)

        def handle_reorder(list_name, action):
            global global_app_data

            pinned = [k for k, v in global_app_data.items() if v.get("pinned", False)]
            unpinned = [k for k, v in global_app_data.items() if not v.get("pinned", False)]
            is_pinned = global_app_data[list_name].get("pinned", False)

            if action == "pin":
                global_app_data[list_name]["pinned"] = True
                unpinned.remove(list_name)
                pinned.append(list_name)
            elif action == "unpin":
                global_app_data[list_name]["pinned"] = False
                pinned.remove(list_name)
                unpinned.insert(0, list_name)
            elif action == "top":
                if is_pinned:
                    pinned.remove(list_name);
                    pinned.insert(0, list_name)
                else:
                    unpinned.remove(list_name);
                    unpinned.insert(0, list_name)
            elif action == "bottom":
                if is_pinned:
                    pinned.remove(list_name);
                    pinned.append(list_name)
                else:
                    unpinned.remove(list_name);
                    unpinned.append(list_name)

            new_ordered_data = {k: global_app_data[k] for k in pinned + unpinned}

            global_app_data.clear()
            global_app_data.update(new_ordered_data)
            trigger_global_sync()

        def create_list_row(list_name):
            is_pinned = global_app_data[list_name].get("pinned", False)

            def delete_list(e=None):
                del global_app_data[list_name]
                trigger_global_sync()

            def rename_list(e=None):
                rename_input = ft.TextField(value=list_name)

                def save_rename(e):
                    new_name = rename_input.value.strip()
                    if new_name and new_name != list_name and new_name not in global_app_data:
                        global_app_data[new_name] = global_app_data.pop(list_name)
                        trigger_global_sync()
                    dialog.open = False
                    page.update()

                def cancel_rename(e):
                    dialog.open = False
                    page.update()

                dialog = ft.AlertDialog(
                    title=ft.Text(f"Rename: {list_name}"),
                    content=rename_input,
                    actions=[ft.TextButton("Cancel", on_click=cancel_rename),
                             ft.TextButton("Save", on_click=save_rename)]
                )
                page.overlay.append(dialog)
                dialog.open = True
                page.update()

            def open_options_menu(e):
                def execute_action(action):
                    menu_dialog.open = False
                    page.update()
                    if action == "rename":
                        rename_list()
                    elif action == "delete":
                        delete_list()
                    else:
                        handle_reorder(list_name, action)

                menu_dialog = ft.AlertDialog(
                    title=ft.Text(f"Options", size=20, weight=ft.FontWeight.BOLD),
                    content=ft.Column([
                        ft.ListTile(leading=ft.Text("📌", size=20),
                                    title=ft.Text("Unpin List" if is_pinned else "Pin List"),
                                    on_click=lambda _: execute_action("unpin" if is_pinned else "pin")),
                        ft.ListTile(leading=ft.Text("⬆️", size=20), title=ft.Text("Move to Top"),
                                    on_click=lambda _: execute_action("top")),
                        ft.ListTile(leading=ft.Text("⬇️", size=20), title=ft.Text("Move to Bottom"),
                                    on_click=lambda _: execute_action("bottom")),
                        ft.Divider(),
                        ft.ListTile(leading=ft.Text("✏️", size=20), title=ft.Text("Rename List"),
                                    on_click=lambda _: execute_action("rename")),
                        ft.ListTile(leading=ft.Text("🗑️", size=20), title=ft.Text("Delete List", color="red"),
                                    on_click=lambda _: execute_action("delete")),
                    ], tight=True),
                    actions=[ft.TextButton("Cancel",
                                           on_click=lambda _: [setattr(menu_dialog, 'open', False), page.update()])]
                )
                page.overlay.append(menu_dialog)
                menu_dialog.open = True
                page.update()

            edit_btn = ft.Container(content=ft.Text("⋮", size=24, weight=ft.FontWeight.BOLD), tooltip="Options",
                                    on_click=open_options_menu, padding=10)

            list_progress = calculate_progress(global_app_data[list_name]["categories"])
            mini_prog_bar = ft.ProgressBar(value=list_progress, color="green", bgcolor="grey200")

            lb_data = global_app_data[list_name]["leaderboards"]
            best_t = f"Timer: {lb_data['timer'][0]['display']}" if lb_data["timer"] else ""
            best_c = f"Clock: {lb_data['clock'][0]['display']}" if lb_data["clock"] else ""

            best_text_str = " | ".join(filter(None, [best_t, best_c]))
            best_text = ft.Text(best_text_str, size=11, color="grey500") if best_text_str else ft.Container()

            subtitle_col = ft.Column(
                [ft.Text(f"{int(list_progress * 100)}% Complete", size=12), mini_prog_bar, best_text], spacing=2)

            return ft.ListTile(
                leading=ft.Text("📌", size=20) if is_pinned else None,
                title=ft.Text(list_name, size=18),
                subtitle=subtitle_col,
                trailing=edit_btn,
                on_click=lambda e: show_list_mode(list_name)
            )

        pinned_keys = [k for k, v in global_app_data.items() if v.get("pinned", False)]
        unpinned_keys = [k for k, v in global_app_data.items() if not v.get("pinned", False)]

        for name in pinned_keys + unpinned_keys:
            lists_view.controls.append(create_list_row(name))

        page.add(ft.SafeArea(
            content=ft.Column([header, ft.Row([new_list_input, add_btn]), ft.Divider(), lists_view], expand=True),
            expand=True))
        page.update()

    # ==========================================
    # 4. LIST MODE VIEW
    # ==========================================
    def show_list_mode(list_name, is_sync=False):
        if not is_sync:
            page.expanded_categories = set()

        page.current_view = f"list:{list_name}"
        page.controls.clear()
        categories = global_app_data[list_name]["categories"]

        header = ft.Row([
            ft.TextButton("← Back", on_click=lambda e: show_main_page()),
            ft.Text(list_name, size=24, weight=ft.FontWeight.BOLD),
        ])

        current_prog = calculate_progress(categories)
        header_prog_bar = ft.ProgressBar(value=current_prog, color="green", bgcolor="grey200", expand=True)
        header_prog_text = ft.Text(f"{int(current_prog * 100)}%", weight=ft.FontWeight.BOLD)

        progress_ui = ft.Row([ft.Text("Progress:"), header_prog_bar, header_prog_text])

        cat_input = ft.TextField(hint_text="Add a new category...", expand=True)
        categories_view = ft.ListView(expand=True, spacing=10)

        def update_live_progress():
            new_prog = calculate_progress(categories)
            header_prog_bar.value = new_prog
            header_prog_text.value = f"{int(new_prog * 100)}%"
            header_prog_bar.update()
            header_prog_text.update()

        def create_category_tile(cat_name, cat_tasks):
            tasks_col = ft.Column()
            cat_title_text = ft.Text(cat_name, size=18, weight=ft.FontWeight.BOLD)

            def handle_expansion(e):
                if str(e.data).lower() == "true":
                    page.expanded_categories.add(cat_name)
                else:
                    page.expanded_categories.discard(cat_name)

            def check_category_completion():
                if len(cat_tasks) > 0 and all(t.get("done", False) for t in cat_tasks):
                    cat_title_text.decoration = ft.TextDecoration.LINE_THROUGH
                    cat_title_text.color = "grey500"
                else:
                    cat_title_text.decoration = ft.TextDecoration.NONE
                    cat_title_text.color = None
                try:
                    cat_title_text.update()
                except:
                    pass

            def edit_task(t):
                edit_task_input = ft.TextField(value=t["text"], label="Task Name")
                edit_weight_input = ft.TextField(value=str(t.get("weight", 1.0)), label="Task Weight (Default 1.0)")

                type_dropdown = ft.Dropdown(
                    label="Time Format",
                    value=t.get("time_type", "duration"),
                    options=[ft.dropdown.Option("duration", "Timer/Duration"),
                             ft.dropdown.Option("clock", "Time of Day")]
                )

                th, tm, ts = "0", "0", "0"
                ch, cm, ampm = "12", "00", "AM"

                if t.get("time"):
                    if t.get("time_type") == "duration":
                        parts = t["time"].split(":")
                        if len(parts) == 3:
                            th, tm, ts = parts[0], parts[1], parts[2]
                        elif len(parts) == 2:
                            tm, ts = parts[0], parts[1]
                        elif len(parts) == 1:
                            ts = parts[0]
                    elif t.get("time_type") == "clock":
                        try:
                            # FIXED THE TYPO HERE!
                            time_part, ampm_part = t["time"].split(" ")
                            ch, cm = time_part.split(":")
                            ampm = ampm_part
                        except:
                            pass

                timer_h = ft.TextField(label="H", width=70, value=th)
                timer_m = ft.TextField(label="M", width=70, value=tm)
                timer_s = ft.TextField(label="S", width=70, value=ts)
                timer_row = ft.Row([timer_h, ft.Text(":"), timer_m, ft.Text(":"), timer_s],
                                   visible=(t.get("time_type", "duration") == "duration"))

                clock_h = ft.TextField(label="H", width=70, value=ch)
                clock_m = ft.TextField(label="M", width=70, value=cm)
                clock_ampm = ft.Dropdown(options=[ft.dropdown.Option("AM"), ft.dropdown.Option("PM")], width=80,
                                         value=ampm)
                edit_date_input = ft.TextField(value=str(t.get("date", "")), label="Date (Optional)", expand=True)
                clock_col = ft.Column([ft.Row([clock_h, ft.Text(":"), clock_m, clock_ampm]), edit_date_input],
                                      visible=(t.get("time_type") == "clock"))

                def on_type_change(e):
                    is_dur = (type_dropdown.value == "duration")
                    timer_row.visible = is_dur
                    clock_col.visible = not is_dur
                    dialog.update()

                type_dropdown.on_change = on_type_change

                def safe_int(val, default=0):
                    try:
                        return int(val)
                    except:
                        return default

                def save_task_edit(e):
                    t["text"] = edit_task_input.value.strip() or t["text"]
                    t["time_type"] = type_dropdown.value
                    if t["time_type"] == "duration":
                        t[
                            "time"] = f"{safe_int(timer_h.value)}:{safe_int(timer_m.value):02d}:{safe_int(timer_s.value):02d}"
                        t["date"] = ""
                    else:
                        h = safe_int(clock_h.value, 12)
                        if h < 1 or h > 12: h = 12
                        m = safe_int(clock_m.value, 0)
                        if m < 0 or m > 59: m = 0
                        t["time"] = f"{h}:{m:02d} {clock_ampm.value}"
                        t["date"] = edit_date_input.value.strip()

                    t["weight"] = safe_int(edit_weight_input.value.strip(), 1)
                    dialog.open = False
                    page.update()
                    trigger_global_sync()

                def delete_task_action(e):
                    cat_tasks.remove(t)
                    dialog.open = False
                    page.update()
                    trigger_global_sync()

                dialog = ft.AlertDialog(
                    title=ft.Text("Edit Task"),
                    content=ft.Column([edit_task_input, edit_weight_input, type_dropdown, timer_row, clock_col],
                                      tight=True),
                    actions=[
                        ft.TextButton("Delete", icon_color="red", on_click=delete_task_action),
                        ft.TextButton("Cancel", on_click=lambda e: [setattr(dialog, 'open', False), page.update()]),
                        ft.TextButton("Save", on_click=save_task_edit)
                    ]
                )
                page.overlay.append(dialog)
                dialog.open = True
                page.update()

            def refresh_tasks():
                tasks_col.controls.clear()
                for task in cat_tasks:
                    def toggle_task(e, t=task):
                        t["done"] = e.control.value
                        trigger_global_sync()

                    time_display = ""
                    if task.get("time") and task.get("time") != "0:00:00":
                        if task.get("time_type") == "clock":
                            date_str = f" - {task.get('date')}" if task.get("date") else ""
                            time_display = f" ({task.get('time')}{date_str})"
                        else:
                            time_display = f" ({task.get('time')})"

                    cb = ft.Checkbox(label=f"{task['text']}{time_display}", value=task["done"], on_change=toggle_task)
                    task_row = ft.Row([cb, ft.TextButton("Edit", on_click=lambda e, t=task: edit_task(t))],
                                      alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                    tasks_col.controls.append(task_row)
                check_category_completion()

            def edit_category(e):
                rename_cat_input = ft.TextField(value=cat_name, label="Category Name")

                def save_cat_edit(e):
                    new_name = rename_cat_input.value.strip()
                    if new_name and new_name != cat_name and new_name not in categories:
                        categories[new_name] = categories.pop(cat_name)
                        # Carry over expansion memory to the new name
                        if cat_name in page.expanded_categories:
                            page.expanded_categories.discard(cat_name)
                            page.expanded_categories.add(new_name)
                        trigger_global_sync()
                    dialog.open = False
                    page.update()

                def delete_cat(e):
                    del categories[cat_name]
                    page.expanded_categories.discard(cat_name)
                    trigger_global_sync()
                    dialog.open = False
                    page.update()

                dialog = ft.AlertDialog(
                    title=ft.Text(f"Edit Category"),
                    content=rename_cat_input,
                    actions=[
                        ft.TextButton("Delete", icon_color="red", on_click=delete_cat),
                        ft.TextButton("Cancel", on_click=lambda e: [setattr(dialog, 'open', False), page.update()]),
                        ft.TextButton("Save", on_click=save_cat_edit)
                    ]
                )
                page.overlay.append(dialog)
                dialog.open = True
                page.update()

            task_input = ft.TextField(hint_text=f"Task for {cat_name}...", expand=True)

            def add_task(e):
                val = task_input.value.strip()
                if val:
                    cat_tasks.append(
                        {"text": val, "done": False, "time": "", "time_type": "duration", "date": "", "weight": 1.0})
                    page.expanded_categories.add(cat_name)  # Ensure it stays open when adding
                    trigger_global_sync()

            add_task_btn = ft.ElevatedButton("Add Task", on_click=add_task)
            refresh_tasks()

            cat_title_row = ft.Row([cat_title_text, ft.TextButton("Edit", on_click=edit_category)],
                                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

            # THE FIX: Changed to expanded=(...)
            expansion_tile = ft.ExpansionTile(
                title=cat_title_row,
                controls=[tasks_col, ft.Row([task_input, add_task_btn])],
                expanded=(cat_name in page.expanded_categories),
                on_change=handle_expansion
            )
            return expansion_tile

        for cat_name, cat_tasks in categories.items():
            categories_view.controls.append(create_category_tile(cat_name, cat_tasks))

        def add_category(e):
            val = cat_input.value.strip()
            if val and val not in categories:
                categories[val] = []
                page.expanded_categories.add(val)  # Pop the new category open automatically
                trigger_global_sync()

        add_cat_btn = ft.ElevatedButton("New Category", on_click=add_category)

        def open_speedrun_setup(e):
            mode_state = ft.Text("timer", visible=False)

            def radio_changed(ev):
                mode_state.value = ev.control.value

            radios = ft.RadioGroup(
                content=ft.Column([
                    ft.Radio(value="timer", label="Timer Mode"),
                    ft.Text("Highlights tasks in red that have not been completed by their set time.", color="grey400",
                            size=12),
                    ft.Divider(height=5, color="transparent"),
                    ft.Radio(value="clock", label="Clock Mode"),
                    ft.Text("Hides (grays out) tasks until their starting time.", color="grey400", size=12),
                ]),
                value="timer",
                on_change=radio_changed
            )

            show_avg_cb = ft.Checkbox(label="Show Average Times")
            show_best_cb = ft.Checkbox(label="Show Best Times")

            def launch_run(ev):
                dialog.open = False
                page.update()
                show_speedrun_mode(list_name, categories, mode_state.value, show_avg_cb.value, show_best_cb.value)

            dialog = ft.AlertDialog(
                title=ft.Text("Speedrun Setup"),
                content=ft.Column([radios, mode_state, ft.Divider(), show_avg_cb, show_best_cb], tight=True),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda ev: [setattr(dialog, 'open', False), page.update()]),
                    ft.ElevatedButton("Start Run!", bgcolor="green", color="white", on_click=launch_run)
                ]
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        def open_leaderboard(e):
            lb_data = global_app_data[list_name]["leaderboards"]

            def create_tab_content(mode_key):
                records = lb_data[mode_key]
                if not records:
                    return ft.Container(content=ft.Row([ft.Text("No records yet.", color="grey")],
                                                       alignment=ft.MainAxisAlignment.CENTER), padding=20)

                lv = ft.ListView(spacing=5, expand=True)
                for i, rec in enumerate(records):
                    def delete_rec(e, idx=i, mk=mode_key):
                        global_app_data[list_name]["leaderboards"][mk].pop(idx)
                        trigger_global_sync()
                        dialog.open = False
                        page.update()
                        open_leaderboard(None)

                    row = ft.Row([
                        ft.Text(f"#{i + 1}", width=30, weight=ft.FontWeight.BOLD),
                        ft.Text(f"{rec['display']}", width=70),
                        ft.Text(f"{rec['date']}", color="grey", size=12, width=80),
                        ft.TextButton("Delete", on_click=delete_rec)
                    ], alignment=ft.MainAxisAlignment.START, spacing=10)
                    lv.controls.append(row)

                def delete_all(e, mk=mode_key):
                    global_app_data[list_name]["leaderboards"][mk] = []
                    trigger_global_sync()
                    dialog.open = False
                    page.update()
                    open_leaderboard(None)

                clear_btn = ft.TextButton("Delete All Records", icon_color="red", on_click=delete_all)
                return ft.Container(content=ft.Column([lv, ft.Divider(), clear_btn]), padding=10, expand=True)

            dynamic_content = ft.Container(content=create_tab_content("timer"), expand=True)

            btn_timer = ft.ElevatedButton("Timer Mode", bgcolor="blue", color="white", expand=True)
            btn_clock = ft.ElevatedButton("Clock Mode", bgcolor="grey800", color="white", expand=True)

            def set_tab(mode):
                if mode == "timer":
                    btn_timer.bgcolor = "blue";
                    btn_clock.bgcolor = "grey800"
                    dynamic_content.content = create_tab_content("timer")
                else:
                    btn_timer.bgcolor = "grey800";
                    btn_clock.bgcolor = "blue"
                    dynamic_content.content = create_tab_content("clock")
                page.update()

            btn_timer.on_click = lambda e: set_tab("timer")
            btn_clock.on_click = lambda e: set_tab("clock")

            dialog = ft.AlertDialog(
                title=ft.Text("Leaderboard 🏆"),
                content=ft.Container(
                    content=ft.Column([ft.Row([btn_timer, btn_clock]), ft.Divider(), dynamic_content], tight=True),
                    width=380, height=350
                ),
                actions=[ft.TextButton("Close", on_click=lambda e: [setattr(dialog, 'open', False), page.update()])]
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        lb_btn = ft.ElevatedButton("🏆", on_click=open_leaderboard, width=65)
        speedrun_btn = ft.ElevatedButton("Start Speedrun ⏱️", bgcolor="green", color="white",
                                         on_click=open_speedrun_setup)

        page.add(ft.SafeArea(content=ft.Column(
            [header, progress_ui, ft.Row([cat_input, add_cat_btn]), ft.Divider(), categories_view,
             ft.Row([lb_btn, speedrun_btn], alignment=ft.MainAxisAlignment.CENTER)], expand=True), expand=True))

    # ==========================================
    # 5. SPEEDRUN EXECUTION MODE
    # ==========================================
    def show_speedrun_mode(list_name, categories, mode, show_avg, show_best):
        page.current_view = f"speedrun:{list_name}"
        page.controls.clear()

        speedrun_state = {"active": True, "completed": False}
        global_start_time = time.time()
        current_run_task_times = {}

        def get_pace_text(task_text):
            lb = global_app_data[list_name]["leaderboards"][mode]
            if not lb: return ""
            times = [entry["task_times"][task_text] for entry in lb if
                     "task_times" in entry and task_text in entry["task_times"]]
            if not times: return ""

            pace_parts = []
            if show_avg:
                avg = sum(times) / len(times)
                m, s = divmod(int(avg), 60);
                h, m = divmod(m, 60)
                pace_parts.append(f"Avg: {h:01d}:{m:02d}:{s:02d}")

            if show_best:
                best = min(times)
                m, s = divmod(int(best), 60);
                h, m = divmod(m, 60)
                pace_parts.append(f"Best: {h:01d}:{m:02d}:{s:02d}")

            return " | ".join(pace_parts)

        def exit_speedrun(e):
            speedrun_state["active"] = False
            show_list_mode(list_name)

        header_btn = ft.TextButton("← Quit Run", on_click=exit_speedrun)

        clock_display = ft.Text("00:00:00", size=50, weight=ft.FontWeight.BOLD, color="green")
        clock_container = ft.Column([clock_display], alignment=ft.MainAxisAlignment.CENTER,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        current_prog = calculate_progress(categories)
        speedrun_prog_bar = ft.ProgressBar(value=current_prog, color="green", bgcolor="grey200", expand=True)
        speedrun_prog_text = ft.Text(f"{int(current_prog * 100)}%", weight=ft.FontWeight.BOLD)

        progress_ui = ft.Row([ft.Text("Progress:"), speedrun_prog_bar, speedrun_prog_text])
        speedrun_view = ft.ListView(expand=True, spacing=10)
        active_ui_refs = []

        def check_all_done():
            total = sum(len(tasks) for tasks in categories.values())
            done = sum(1 for tasks in categories.values() for t in tasks if t.get("done"))
            return total > 0 and done == total

        def resume_run(e=None):
            speedrun_state["completed"] = False
            clock_container.controls.clear()
            clock_container.controls.append(clock_display)
            page.update()

        def mark_completed():
            speedrun_state["completed"] = True
            final_time_str = clock_display.value
            today_str = datetime.now().strftime("%m/%d/%Y")

            if mode == "timer":
                sort_val = int(time.time() - global_start_time)
            else:
                now_t = datetime.now().time()
                sort_val = now_t.hour * 3600 + now_t.minute * 60 + now_t.second

            entry = {"sort_val": sort_val, "display": final_time_str, "date": today_str,
                     "task_times": current_run_task_times}
            lb = global_app_data[list_name]["leaderboards"][mode]
            lb.append(entry)
            lb.sort(key=lambda x: x["sort_val"])
            trigger_global_sync()

            clock_container.controls.clear()
            clock_container.controls.append(
                ft.Text("Speedrun Complete!", size=24, color="green", weight=ft.FontWeight.BOLD))
            clock_container.controls.append(ft.Text(final_time_str, size=40, weight=ft.FontWeight.BOLD))
            clock_container.controls.append(ft.ElevatedButton("Resume", on_click=resume_run))
            page.update()

        for cat_name, cat_tasks in categories.items():
            tasks_col = ft.Column()
            for t in cat_tasks:
                time_display = ""
                if t.get("time") and t.get("time") != "0:00:00":
                    time_display = f"  [{t.get('time')}]"

                pace_str = get_pace_text(t["text"])
                pace_text = ft.Text(pace_str, size=11, color="grey500") if pace_str else ft.Container()

                task_text = ft.Text(f"{t['text']}{time_display}", size=16)
                task_col = ft.Column([task_text, pace_text], spacing=0)

                cb = ft.Checkbox(value=t["done"])

                def make_toggle(task_dict):
                    def toggle(e):
                        task_dict["done"] = e.control.value
                        if e.control.value:
                            current_run_task_times[task_dict["text"]] = int(time.time() - global_start_time)

                        trigger_global_sync()  # Whisper to everyone that a box was checked!

                        new_prog = calculate_progress(categories)
                        speedrun_prog_bar.value = new_prog
                        speedrun_prog_text.value = f"{int(new_prog * 100)}%"

                        is_all_done = check_all_done()
                        if is_all_done and not speedrun_state["completed"]:
                            mark_completed()
                        elif not is_all_done and speedrun_state["completed"]:
                            resume_run()
                        else:
                            page.update()

                    return toggle

                cb.on_change = make_toggle(t)
                task_row = ft.Row([cb, task_col])
                tasks_col.controls.append(task_row)
                active_ui_refs.append((t, task_row, task_text))

            # Ensure speedrun view categories are always expanded
            cat_tile = ft.ExpansionTile(title=ft.Text(cat_name, size=18, weight=ft.FontWeight.BOLD),
                                        controls=[tasks_col], expanded=True)
            speedrun_view.controls.append(cat_tile)

        page.add(ft.SafeArea(content=ft.Column(
            [header_btn, ft.Row([clock_container], alignment=ft.MainAxisAlignment.CENTER), progress_ui, ft.Divider(),
             speedrun_view], expand=True), expand=True))

        async def timer_loop():
            while speedrun_state["active"]:
                now = datetime.now()

                if mode == "timer":
                    elapsed = int(time.time() - global_start_time)
                    m, s = divmod(elapsed, 60);
                    h, m = divmod(m, 60)
                    clock_display.value = f"{h:01d}:{m:02d}:{s:02d}"

                    for task_dict, row_ui, text_ui in active_ui_refs:
                        if not task_dict.get("done") and task_dict.get("time_type") == "duration" and task_dict.get(
                                "time"):
                            limit_sec = parse_duration(task_dict["time"])
                            if limit_sec and elapsed > limit_sec:
                                if text_ui.color != "red": text_ui.color = "red"
                            else:
                                if text_ui.color == "red": text_ui.color = None

                elif mode == "clock":
                    clock_display.value = now.strftime("%I:%M:%S %p")
                    current_time_obj = now.time()

                    for task_dict, row_ui, text_ui in active_ui_refs:
                        if task_dict.get("time_type") == "clock" and task_dict.get("time"):
                            target_time = parse_clock(task_dict["time"])
                            if target_time:
                                if current_time_obj < target_time:
                                    if not row_ui.disabled:
                                        row_ui.disabled = True
                                        row_ui.opacity = 0.4
                                else:
                                    if row_ui.disabled:
                                        row_ui.disabled = False
                                        row_ui.opacity = 1.0

                if not speedrun_state["completed"]:
                    try:
                        page.update()
                    except:
                        pass

                await asyncio.sleep(1)

        page.run_task(timer_loop)

    # Boot up the Main Page
    show_main_page()


# Launching as a Web Server!
if __name__ == "__main__":
    # Ask the cloud server for a port, but default to 8550 if running locally
    port = int(os.environ.get("PORT", 8550))
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=port, host="0.0.0.0")