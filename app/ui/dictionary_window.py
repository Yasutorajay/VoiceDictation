from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from app.dictionary_manager import DictionaryManager


class DictionaryWindow:
    """词库管理窗口：列表可滚动，底部操作区始终可见。"""

    WIDTH = 640
    HEIGHT = 420

    def __init__(self, manager: DictionaryManager) -> None:
        self.manager = manager
        self.root: tk.Tk | tk.Toplevel | None = None

    def open(self) -> None:
        if self.root is not None and self.root.winfo_exists():
            self.root.lift()
            return
        root = tk.Toplevel() if tk._default_root else tk.Tk()
        self.root = root
        root.title("VoiceDictation · 词库管理")
        root.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        root.minsize(self.WIDTH, self.HEIGHT)
        root.configure(bg="#08111f")
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="词库管理", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="已安装词库及其来源、许可证信息。使用右侧滚轮查看完整列表。",
            foreground="#555",
        ).pack(anchor="w", pady=(4, 10))

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(list_frame, columns=("source", "license"), show="headings", selectmode="browse")
        tree.heading("source", text="来源")
        tree.heading("license", text="许可证")
        tree.column("source", width=340, minwidth=180, stretch=True)
        tree.column("license", width=180, minwidth=120, stretch=False)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._refresh(tree)

        term_actions = ttk.Frame(frame)
        term_actions.pack(fill="x", pady=(10, 4))
        ttk.Button(term_actions, text="添加自定义词条", command=lambda: self._edit_term(root, tree)).pack(side="left")
        ttk.Button(term_actions, text="编辑词条", command=lambda: self._edit_term(root, tree, edit=True)).pack(side="left", padx=8)
        ttk.Button(term_actions, text="删除词条", command=lambda: self._remove_term(root, tree)).pack(side="left")
        package_actions = ttk.Frame(frame)
        package_actions.pack(fill="x")
        ttk.Button(package_actions, text="导入词库包", command=lambda: self._import(root, tree)).pack(side="left")
        ttk.Button(package_actions, text="从 HTTPS 下载", command=lambda: self._download(root, tree)).pack(side="left", padx=8)
        ttk.Button(package_actions, text="删除选中词库", command=lambda: self._remove(tree)).pack(side="left")
        ttk.Button(package_actions, text="关闭", command=root.destroy).pack(side="right")
        if isinstance(root, tk.Tk):
            root.mainloop()

    def _refresh(self, tree: ttk.Treeview) -> None:
        tree.delete(*tree.get_children())
        for package in self.manager.all_packages():
            tree.insert("", "end", iid=package.id, values=(package.url, package.license))
        self._term_rows(tree)

    def _import(self, root: tk.Misc, tree: ttk.Treeview) -> None:
        source = filedialog.askopenfilename(parent=root, filetypes=[("词库", "*.yaml *.yml *.json")])
        if not source:
            return
        package_id = Path(source).stem
        try:
            self.manager.import_file(Path(source), package_id, "用户导入；请自行确认来源和商业许可证")
            self._refresh(tree)
            messagebox.showinfo("导入成功", f"已导入：{package_id}", parent=root)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=root)

    def _remove(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if not selected:
            return
        package_id = selected[0]
        if package_id.startswith("term:"):
            return
        if not messagebox.askyesno("删除词库", f"确定删除词库“{package_id}”吗？", parent=tree):
            return
        try:
            self.manager.remove(package_id)
            tree.delete(package_id)
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=tree)

    def _download(self, root: tk.Misc, tree: ttk.Treeview) -> None:
        url = simpledialog.askstring("下载词库", "请输入 YAML/JSON 词库的 HTTPS 地址：", parent=root)
        if not url:
            return
        package_id = simpledialog.askstring("词库名称", "请输入词库名称（字母、数字、- 或 _）：", parent=root)
        if not package_id:
            return
        try:
            self.manager.download_url(url.strip(), package_id.strip())
            self._refresh(tree)
            messagebox.showinfo("下载成功", "词库已安装，重启程序后生效。", parent=root)
        except Exception as exc:
            messagebox.showerror("下载失败", str(exc), parent=root)

    def _term_rows(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            if str(item).startswith("term:"):
                tree.delete(item)
        for term in self.manager.list_user_terms():
            canonical = str(term.get("canonical", ""))
            if canonical:
                aliases = ", ".join(str(a) for a in term.get("aliases", []))
                tree.insert("", "end", iid=f"term:{canonical}", values=(canonical, aliases))

    def _edit_term(self, root: tk.Misc, tree: ttk.Treeview, edit: bool = False) -> None:
        selected = tree.selection()[0] if edit and tree.selection() else ""
        original = selected.removeprefix("term:") if selected.startswith("term:") else None
        current = next((term for term in self.manager.list_user_terms() if term.get("canonical") == original), {})
        canonical = simpledialog.askstring("自定义词条", "请输入规范词（最终显示内容）：", initialvalue=current.get("canonical", ""), parent=root)
        if not canonical:
            return
        aliases = simpledialog.askstring("自定义词条", "请输入误识别/口语写法，用逗号分隔：", initialvalue=", ".join(current.get("aliases", [])), parent=root)
        if not aliases:
            return
        try:
            self.manager.save_user_term(canonical, aliases.replace("，", ",").split(","), original)
            self._refresh(tree)
            messagebox.showinfo("保存成功", "词条已保存，重启程序后生效。", parent=root)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=root)

    def _remove_term(self, root: tk.Misc, tree: ttk.Treeview) -> None:
        selected = tree.selection()[0] if tree.selection() else ""
        if not selected.startswith("term:"):
            return
        try:
            self.manager.remove_user_term(selected.removeprefix("term:"))
            tree.delete(selected)
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc), parent=root)
