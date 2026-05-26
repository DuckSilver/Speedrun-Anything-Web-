import flet as ft
import json
import os
import time
import asyncio
from datetime import datetime
from pymongo import MongoClient

# Set up permanent folders for the Import/Export engine
ASSETS_DIR = "assets"
UPLOAD_DIR = "uploads"
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==========================================
# 1. THE GLOBAL BRAIN (NOW POWERED BY MONGODB!)
# ==========================================
global_app_data = {}

# Connect to your MongoDB Cloud Cluster
MONGO_URI = "mongodb+srv://Duckd:QFTPHdUCsIvLzVCT@speedruncluster.nf8tuia.mongodb.net/?appName=SpeedrunCluster"
try:
    client = MongoClient(MONGO_URI)
    db = client["speedrun_database"]  # Creates a database
    collection = db["save_data"]  # Creates a collection (folder) inside it
except Exception as e:
    print(f"Database connection error: {e}")


def load_server_data():
    global global_app_data
    try:
        # Ask MongoDB for the master save file
        document = collection.find_one({"_id": "master_save"})
        if document and "data" in document:
            global_app_data = document["data"]
        else:
            global_app_data = {}
    except Exception:
        global_app_data = {}


def save_server_data():
    global global_app_data
    try:
        # Overwrite the master save file in MongoDB with the newest data
        collection.update_one(
            {"_id": "master_save"},
            {"$set": {"data": global_app_data}},
            upsert=True  # If the file doesn't exist yet, create it!
        )
    except Exception:
        pass


# Pull the data from the cloud when the server turns on
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
    page.theme_mode = ft.ThemeMode.DARK

    # User's Session Memory
    page.current_room = None
    page.current_view = "login"

    # ==========================================
    # 2. THE WHISPER NETWORK (ISOLATED ROOMS)
    # ==========================================
    def on_broadcast(message):
        if message.get("room") != page.current_room:
            return

        current_view = getattr(page, "current_view", None)
        if current_view == "main":
            show_main_page(is_sync=True)
        elif current_view and current_view.startswith("list:"):
            target_list = current_view.split(":", 1)[1]
            if target_list in global_app_data[page.current_room]["lists"]:
                show_list_mode(target_list, is_sync=True)
        elif current_view and current_view.startswith("speedrun:"):
            target_list = current_view.split(":", 1)[1]
            if target_list in global_app_data[page.current_room]["lists"]:
                page.update()

    page.pubsub.subscribe(on_broadcast)

    def trigger_global_sync():
        save_server_data()
        page.pubsub.send_all({"room": page.current_room})

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
    # 3. THE LOBBY (LOGIN PAGE)
    # ==========================================
    def show_login_page():
        page.current_view = "login"
        page.current_room = None
        page.controls.clear()

        title = ft.Text("Speedrun Hub", size=40, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
        subtitle = ft.Text("Join or create a shared room", color="grey500")

        room_input = ft.TextField(label="🚪 Room Name")
        pass_input = ft.TextField(label="🔒 Password", password=True, can_reveal_password=True)
        error_text = ft.Text("", color="red", visible=False)

        def attempt_login(e):
            r_name = room_input.value.strip()
            r_pass = pass_input.value.strip()

            if not r_name or not r_pass:
                error_text.value = "Please enter both a Room Name and Password."
                error_text.visible = True
                page.update()
                return

            global global_app_data

            if r_name in global_app_data:
                if global_app_data[r_name]["password"] == r_pass:
                    page.current_room = r_name
                    show_main_page()
                else:
                    error_text.value = "Incorrect password for this room."
                    error_text.visible = True
                    page.update()
            else:
                global_app_data[r_name] = {
                    "password": r_pass,
                    "lists": {}
                }
                save_server_data()
                page.current_room = r_name
                show_main_page()

        join_btn = ft.ElevatedButton("Enter Room", bgcolor="blue", color="white", width=200, height=50,
                                     on_click=attempt_login)

        page.add(
            ft.SafeArea(
                content=ft.Column(
                    [
                        ft.Container(expand=True),
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        title,
                                        subtitle,
                                        ft.Container(height=30),
                                        room_input,
                                        pass_input,
                                        error_text,
                                        ft.Container(height=20),
                                        join_btn
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                )
                            ],
                            alignment=ft.MainAxisAlignment.CENTER
                        ),
                        ft.Container(expand=True),
                        ft.Row(
                            [ft.Text("v1.6", size=12, color="grey500")],
                            alignment=ft.MainAxisAlignment.END
                        )
                    ],
                    expand=True
                ),
                expand=True
            )
        )
        page.update()

    # ==========================================
    # 4. MAIN PAGE VIEW (INSIDE A ROOM)
    # ==========================================
    def show_main_page(is_sync=False):
        page.current_view = "main"
        page.controls.clear()

        room_lists = global_app_data[page.current_room]["lists"]

        header = ft.Row([
            ft.Text(f"Room: {page.current_room}", size=26, weight=ft.FontWeight.BOLD, expand=True),
            ft.TextButton("🚪 Leave Room", on_click=lambda e: show_login_page())
        ])

        new_list_input = ft.TextField(hint_text="Name a new checklist...", expand=True)

        def add_list_clicked(e):
            name = new_list_input.value.strip()
            if name and name not in room_lists:
                room_lists[name] = {
                    "categories": {},
                    "leaderboards": {"timer": [], "clock": []},
                    "pinned": False
                }
                trigger_global_sync()

        def open_import_dialog(e):
            name_input = ft.TextField(label="New List Name", value="Imported List")
            import_input = ft.TextField(label="Paste copied list data here...", multiline=True, min_lines=5,
                                        max_lines=8)
            import_error = ft.Text("", color="red", visible=False)

            def process_import(ev):
                list_name = name_input.value.strip() or "Imported List"
                raw_text = import_input.value.strip()

                if list_name in room_lists:
                    import_error.value = "A list with this name already exists in this room."
                    import_error.visible = True
                    dialog.update()
                    return

                if not raw_text:
                    import_error.value = "Please paste the list data."
                    import_error.visible = True
                    dialog.update()
                    return

                try:
                    imported_data = json.loads(raw_text)
                    if "categories" in imported_data:
                        room_lists[list_name] = imported_data
                        trigger_global_sync()
                        dialog.open = False
                        page.update()
                    else:
                        import_error.value = "This does not look like valid Speedrun data."
                        import_error.visible = True
                        dialog.update()
                except Exception:
                    import_error.value = "Invalid format. Make sure you copied the entire block of text."
                    import_error.visible = True
                    dialog.update()

            dialog = ft.AlertDialog(
                title=ft.Text("📂 Import List"),
                content=ft.Column([
                    name_input,
                    import_input,
                    import_error
                ], tight=True),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: [setattr(dialog, 'open', False), page.update()]),
                    ft.ElevatedButton("Import", bgcolor="blue", color="white", on_click=process_import)
                ]
            )
            page.overlay.append(dialog)
            dialog.open = True
            page.update()

        add_btn = ft.ElevatedButton("Create", on_click=add_list_clicked)
        import_btn = ft.ElevatedButton("📂 Import", bgcolor="grey800", color="white", on_click=open_import_dialog)

        lists_view = ft.ListView(expand=True, spacing=5)

        def handle_reorder(list_name, action):
            pinned = [k for k, v in room_lists.items() if v.get("pinned", False)]
            unpinned = [k for k, v in room_lists.items() if not v.get("pinned", False)]
            is_pinned = room_lists[list_name].get("pinned", False)

            if action == "pin":
                room_lists[list_name]["pinned"] = True
                unpinned.remove(list_name)
                pinned.append(list_name)
            elif action == "unpin":
                room_lists[list_name]["pinned"] = False
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

            new_ordered_data = {k: room_lists[k] for k in pinned + unpinned}
            global_app_data[page.current_room]["lists"].clear()
            global_app_data[page.current_room]["lists"].update(new_ordered_data)
            trigger_global_sync()

        def create_list_row(list_name):
            is_pinned = room_lists[list_name].get("pinned", False)

            def delete_list(e=None):
                del room_lists[list_name]
                trigger_global_sync()

            def rename_list(e=None):
                rename_input = ft.TextField(value=list_name)

                def save_rename(e):
                    new_name = rename_input.value.strip()
                    if new_name and new_name != list_name and new_name not in room_lists:
                        room_lists[new_name] = room_lists.pop(list_name)
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
                    elif action == "export":
                        json_str = json.dumps(room_lists[list_name])
                        export_input = ft.TextField(value=json_str, multiline=True, min_lines=5, max_lines=8,
                                                    read_only=True, label="Raw Data")

                        def try_auto_copy(ev):
                            page.clipboard.set(json_str)
                            snack = ft.SnackBar(ft.Text(f"Attempted to copy '{list_name}' to clipboard!"))
                            page.overlay.append(snack)
                            snack.open = True
                            export_dialog.open = False
                            page.update()

                        export_dialog = ft.AlertDialog(
                            title=ft.Text("📋 Export List"),
                            content=ft.Column([
                                ft.Text(
                                    "If the Auto-Copy button fails, manually highlight and copy (Ctrl+C) the text below:",
                                    size=12, color="grey400"),
                                export_input
                            ], tight=True),
                            actions=[
                                ft.TextButton("Close", on_click=lambda _: [setattr(export_dialog, 'open', False),
                                                                           page.update()]),
                                ft.ElevatedButton("Auto-Copy", bgcolor="blue", color="white", on_click=try_auto_copy)
                            ]
                        )
                        page.overlay.append(export_dialog)
                        export_dialog.open = True
                        page.update()
                    else:
                        handle_reorder(list_name, action)

                menu_dialog = ft.AlertDialog(
                    title=ft.Text(f"Options", size=20, weight=ft.FontWeight.BOLD),
                    content=ft.Column([
                        ft.TextButton("📌 Pin/Unpin List",
                                      on_click=lambda _: execute_action("unpin" if is_pinned else "pin")),
                        ft.TextButton("⬆️ Move to Top", on_click=lambda _: execute_action("top")),
                        ft.TextButton("⬇️ Move to Bottom", on_click=lambda _: execute_action("bottom")),
                        ft.Divider(height=5),
                        ft.TextButton("✏️ Rename List", on_click=lambda _: execute_action("rename")),
                        ft.TextButton("📋 Copy List Data", on_click=lambda _: execute_action("export")),
                        ft.TextButton("🗑️ Delete List", icon_color="red", on_click=lambda _: execute_action("delete")),
                    ], tight=True, alignment=ft.MainAxisAlignment.START),
                    actions=[ft.TextButton("Cancel",
                                           on_click=lambda _: [setattr(menu_dialog, 'open', False), page.update()])]
                )
                page.overlay.append(menu_dialog)
                menu_dialog.open = True
                page.update()

            edit_btn = ft.Container(content=ft.Text("⋮", size=24, weight=ft.FontWeight.BOLD), tooltip="Options",
                                    on_click=open_options_menu, padding=10)

            list_progress = calculate_progress(room_lists[list_name]["categories"])
            mini_prog_bar = ft.ProgressBar(value=list_progress, color="green", bgcolor="grey200")

            lb_data = room_lists[list_name]["leaderboards"]
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

        pinned_keys = [k for k, v in room_lists.items() if v.get("pinned", False)]
        unpinned_keys = [k for k, v in room_lists.items() if not v.get("pinned", False)]

        for name in pinned_keys + unpinned_keys:
            lists_view.controls.append(create_list_row(name))

        page.add(ft.SafeArea(
            content=ft.Column([header, ft.Row([new_list_input, add_btn, import_btn]), ft.Divider(), lists_view],
                              expand=True), expand=True))
        page.update()

    # ==========================================
    # 5. LIST MODE VIEW
    # ==========================================
    def show_list_mode(list_name, is_sync=False):
        if not is_sync:
            page.expanded_categories = set()

        page.current_view = f"list:{list_name}"
        page.controls.clear()

        room_lists = global_app_data[page.current_room]["lists"]
        categories = room_lists[list_name]["categories"]

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
                    page.expanded_categories.add(cat_name)
                    trigger_global_sync()

            add_task_btn = ft.ElevatedButton("Add Task", on_click=add_task)
            refresh_tasks()

            cat_title_row = ft.Row([cat_title_text, ft.TextButton("Edit", on_click=edit_category)],
                                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

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
                page.expanded_categories.add(val)
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
            lb_data = room_lists[list_name]["leaderboards"]

            def create_tab_content(mode_key):
                records = lb_data[mode_key]
                if not records:
                    return ft.Container(content=ft.Row([ft.Text("No records yet.", color="grey")],
                                                       alignment=ft.MainAxisAlignment.CENTER), padding=20)

                lv = ft.ListView(spacing=5, expand=True)
                for i, rec in enumerate(records):
                    def delete_rec(e, idx=i, mk=mode_key):
                        room_lists[list_name]["leaderboards"][mk].pop(idx)
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
                    room_lists[list_name]["leaderboards"][mk] = []
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
    # 6. SPEEDRUN EXECUTION MODE
    # ==========================================
    def show_speedrun_mode(list_name, categories, mode, show_avg, show_best):
        page.current_view = f"speedrun:{list_name}"
        page.controls.clear()

        room_lists = global_app_data[page.current_room]["lists"]

        speedrun_state = {"active": True, "completed": False}
        global_start_time = time.time()
        current_run_task_times = {}

        def format_time_val(val_sec, mode_type):
            m, s = divmod(int(val_sec), 60)
            h, m = divmod(m, 60)
            if mode_type == "timer":
                return f"{h:01d}:{m:02d}:{s:02d}"
            else:
                am_pm = "AM"
                if h >= 12:
                    am_pm = "PM"
                    if h > 12:
                        h -= 12
                if h == 0:
                    h = 12
                return f"{h}:{m:02d}:{s:02d} {am_pm}"

        def get_pace_text(task_text):
            lb = room_lists[list_name]["leaderboards"][mode]
            if not lb: return ""
            times = [entry["task_times"][task_text] for entry in lb if
                     "task_times" in entry and task_text in entry["task_times"]]
            if not times: return ""

            pace_parts = []
            if show_avg:
                avg = sum(times) / len(times)
                pace_parts.append(f"Avg: {format_time_val(avg, mode)}")

            if show_best:
                best = min(times)
                pace_parts.append(f"Best: {format_time_val(best, mode)}")

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
            lb = room_lists[list_name]["leaderboards"][mode]
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
                            if mode == "timer":
                                current_run_task_times[task_dict["text"]] = int(time.time() - global_start_time)
                            else:
                                now_t = datetime.now()
                                current_run_task_times[
                                    task_dict["text"]] = now_t.hour * 3600 + now_t.minute * 60 + now_t.second

                        trigger_global_sync()

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

    show_login_page()


# Launching as a Web Server!
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8550))
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=port, host="0.0.0.0", assets_dir=ASSETS_DIR,
           upload_dir=UPLOAD_DIR)
