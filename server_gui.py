import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
from server_core import FTPServerCore

class FTPServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hybrid FTP Server")
        self.root.geometry("900x600")
        self.root.minsize(800, 500)
        self.root.configure(bg="#1E1E1E") 

        self.build_ui()
        self.write_log("[SYSTEM] Đang khởi động lõi TCP Server...")
        
        self.core_server = FTPServerCore(self.write_log, self.update_dashboard)
        threading.Thread(target=self.core_server.start, daemon=True).start()
        
        # Kích hoạt luồng refresh UI mỗi giây để Uptime và Speed hiển thị real-time
        self.auto_refresh()

    def build_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", background="#2D2D2D", foreground="white", fieldbackground="#2D2D2D", borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#3C3C3C", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map('Treeview', background=[('selected', '#0078D7')])

        top_frame = tk.Frame(self.root, bg="#1E1E1E")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        tk.Label(top_frame, text="DANH SÁCH CLIENT ĐANG KẾT NỐI", bg="#1E1E1E", fg="#4FC1FF", font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(fill=tk.X, pady=(0, 5))

        # ĐÃ THAY ĐỔI THEO YÊU CẦU: IP, User, Trạng Thái, Tốc Độ, Thời Gian (Uptime)
        columns = ("ip", "user", "status", "speed", "uptime")
        self.tree = ttk.Treeview(top_frame, columns=columns, show="headings", height=8)
        self.tree.heading("ip", text="IP:PORT")
        self.tree.heading("user", text="USERNAME")
        self.tree.heading("status", text="TRẠNG THÁI")
        self.tree.heading("speed", text="TỐC ĐỘ (KB/s)")
        self.tree.heading("uptime", text="THỜI GIAN KẾT NỐI")
        
        self.tree.column("ip", width=120, anchor=tk.CENTER)
        self.tree.column("user", width=80, anchor=tk.CENTER)
        self.tree.column("status", width=250, anchor=tk.W)
        self.tree.column("speed", width=120, anchor=tk.CENTER)
        self.tree.column("uptime", width=120, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Bổ sung Context Menu Chuột Phải
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="❌ Ngắt kết nối Client (Disconnect)", command=self.disconnect_client)

        bot_frame = tk.Frame(self.root, bg="#1E1E1E")
        bot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        tk.Label(bot_frame, text="SERVER TERMINAL LOGS", bg="#1E1E1E", fg="#4FC1FF", font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(fill=tk.X, pady=(0, 5))
        
        self.log_area = scrolledtext.ScrolledText(bot_frame, state='disabled', bg="#0C0C0C", fg="#CCCCCC", font=("Consolas", 10), bd=0, padx=10, pady=10)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def write_log(self, message):
        def _append():
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, f"{time.strftime('%H:%M:%S')} | {message}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')
        self.root.after(0, _append)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def disconnect_client(self):
        selected = self.tree.selection()
        if not selected: return
        item = self.tree.item(selected[0])
        ip_port_str = item['values'][0]
        
        # IMPORT THÊM client_lock TỪ LÕI
        from server_core import active_clients, client_lock 
        
        # BỌC KHÓA LẠI ĐỂ TRÁNH ĐỤNG ĐỘ KHI ADMIN ĐANG KICK MÀ CLIENT LẠI TỰ THOÁT
        with client_lock:
            for addr, info in list(active_clients.items()):
                if f"{addr[0]}:{addr[1]}" == ip_port_str:
                    try:
                        info["conn"].close() 
                        self.write_log(f"[!] Admin đã ngắt kết nối thủ công Client {ip_port_str}")
                    except Exception: pass
                    break

    def auto_refresh(self):
        self.update_dashboard()
        self.root.after(1000, self.auto_refresh)

    def update_dashboard(self):
        def _refresh():
            # IMPORT THÊM client_lock TỪ LÕI
            from server_core import active_clients, client_lock 
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # COPY DỮ LIỆU NHANH TRONG LÚC KHÓA ĐỂ TRÁNH LỖI DUYỆT
            with client_lock:
                clients_snap = list(active_clients.items())
            
            # DUYỆT VÀ VẼ LÊN GIAO DIỆN TỪ BẢN COPY (clients_snap)
            for c_addr, info in clients_snap:
                addr_str = f"{c_addr[0]}:{c_addr[1]}"
                
                duration = int(time.time() - info['connect_time'])
                m, s = divmod(duration, 60)
                h, m = divmod(m, 60)
                uptime_str = f"{m:02d}:{s:02d}" if h == 0 else f"{h:02d}:{m:02d}:{s:02d}"
                
                self.tree.insert("", tk.END, values=(addr_str, info['user'], info['status'], info['speed'], uptime_str))
        self.root.after(0, _refresh)

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPServerGUI(root)
    root.mainloop()