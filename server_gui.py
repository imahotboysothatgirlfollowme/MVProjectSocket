import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
from server_core import FTPServerCore

class FTPServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hybrid FTP Server - Control Panel")
        self.root.geometry("850x600")
        self.root.minsize(700, 500)
        self.root.configure(bg="#1E1E1E") 

        self.build_ui()
        
        self.write_log("[SYSTEM] Đang khởi động lõi TCP Server...")
        
        # Khởi tạo Lõi Server từ module server_core.py và chạy ngầm
        self.core_server = FTPServerCore(self.write_log, self.update_dashboard)
        threading.Thread(target=self.core_server.start, daemon=True).start()

    def build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", background="#2D2D2D", foreground="white", fieldbackground="#2D2D2D", borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#3C3C3C", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map('Treeview', background=[('selected', '#0078D7')])

        top_frame = tk.Frame(self.root, bg="#1E1E1E")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        tk.Label(top_frame, text="DANH SÁCH CLIENT ĐANG KẾT NỐI", bg="#1E1E1E", fg="#4FC1FF", font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(fill=tk.X, pady=(0, 5))

        columns = ("ip", "user", "status", "mode", "type_mode")
        self.tree = ttk.Treeview(top_frame, columns=columns, show="headings", height=8)
        self.tree.heading("ip", text="IP:PORT")
        self.tree.heading("user", text="USERNAME")
        self.tree.heading("status", text="TRẠNG THÁI")
        self.tree.heading("mode", text="MẠNG (ACT/PASV)")
        self.tree.heading("type_mode", text="ĐỊNH DẠNG/CHẾ ĐỘ")
        
        self.tree.column("ip", width=120, anchor=tk.CENTER)
        self.tree.column("user", width=80, anchor=tk.CENTER)
        self.tree.column("status", width=250, anchor=tk.W)
        self.tree.column("mode", width=120, anchor=tk.CENTER)
        self.tree.column("type_mode", width=120, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)

        bot_frame = tk.Frame(self.root, bg="#1E1E1E")
        bot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        tk.Label(bot_frame, text="SERVER TERMINAL LOGS", bg="#1E1E1E", fg="#4FC1FF", font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(fill=tk.X, pady=(0, 5))
        
        self.log_area = scrolledtext.ScrolledText(bot_frame, state='disabled', bg="#0C0C0C", fg="#CCCCCC", font=("Consolas", 10), bd=0, padx=10, pady=10)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def write_log(self, message):
        """Callback: Được truyền vào server_core để hiển thị log an toàn"""
        def _append():
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, f"{time.strftime('%H:%M:%S')} | {message}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')
        self.root.after(0, _append)

    def update_dashboard(self):
        """Callback: Được truyền vào server_core để load lại Treeview an toàn"""
        def _refresh():
            # Import biến active_clients từ file server_core để lấy dữ liệu mới nhất
            from server_core import active_clients 
            
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            for c_addr, info in active_clients.items():
                addr_str = f"{c_addr[0]}:{c_addr[1]}"
                type_mode = f"{info['data_type']} / {info['tran_mode']}"
                self.tree.insert("", tk.END, values=(addr_str, info['user'], info['status'], info['mode'], type_mode))
        self.root.after(0, _refresh)

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPServerGUI(root)
    root.mainloop()