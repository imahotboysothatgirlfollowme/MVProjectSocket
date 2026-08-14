import hashlib
import socket
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from tkinter import simpledialog, filedialog
import re
import os
from rdt_core import rdt_receive, rdt_send

class FTPClientGUI:
    def __init__(self, root):
        self.client_data_type = "I" # Loại bỏ UI cho TYPE, hardcode 99% dùng Binary
        self.root = root
        self.build_ui()

    def build_ui(self):
        self.root.title("Hybrid FTP Client - Smart File Browser")
        self.root.geometry("1000x650")
        self.root.minsize(900, 600)
        self.root.configure(bg="#F3F4F6")
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Sidebar.TFrame", background="#FFFFFF")
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=5)
        
        main_container = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bd=0, bg="#E5E7EB")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        sidebar = ttk.Frame(main_container, style="Sidebar.TFrame", width=280)
        main_container.add(sidebar, minsize=280)

        form_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
        form_frame.pack(fill=tk.X, padx=20, pady=(20, 0))
        
        self.ip_var, self.port_var = tk.StringVar(value="127.0.0.1"), tk.StringVar(value="2121")
        self.user_var, self.pass_var = tk.StringVar(value="admin"), tk.StringVar(value="123456")

        def create_input(parent, label_text, var, is_password=False):
            ttk.Label(parent, text=label_text, font=("Segoe UI", 9, "bold"), background="#FFFFFF").pack(anchor=tk.W, pady=(10, 2))
            entry = ttk.Entry(parent, font=("Consolas", 10), textvariable=var, show="*" if is_password else "")
            entry.pack(fill=tk.X, ipady=4)
            return entry

        create_input(form_frame, "Server IP:", self.ip_var)
        create_input(form_frame, "Command Port:", self.port_var)
        create_input(form_frame, "Username:", self.user_var)
        create_input(form_frame, "Password:", self.pass_var, is_password=True)
        
        self.use_pasv_var = tk.BooleanVar(value=True) 
        tk.Checkbutton(sidebar, text=" Bật Passive Mode (PASV)", variable=self.use_pasv_var, bg="#FFFFFF").pack(anchor=tk.W, padx=20, pady=20)
        
        self.btn_connect = tk.Button(sidebar, text="KẾT NỐI SERVER", bg="#2563EB", fg="white", font=("Segoe UI", 10, "bold"), command=self.start_connection)
        self.btn_connect.pack(fill=tk.X, padx=20, pady=(0, 20), ipady=8)

        content_frame = ttk.Frame(main_container)
        main_container.add(content_frame)
        
        action_frame = tk.Frame(content_frame, bg="#FFFFFF", bd=0, highlightbackground="#D1D5DB", highlightthickness=1)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        btn_container = tk.Frame(action_frame, bg="#FFFFFF")
        btn_container.pack(padx=15, pady=10, anchor=tk.W)
        
        self.btn_list = ttk.Button(btn_container, text="🔄 Làm mới (Refresh)", style="Action.TButton", state="disabled", command=self.list_files)
        self.btn_list.grid(row=0, column=0, padx=(0, 10))
        
        self.btn_stor = ttk.Button(btn_container, text="⬆️ Tải lên (Upload)", style="Action.TButton", state="disabled", command=self.upload_file)
        self.btn_stor.grid(row=0, column=1, padx=(0, 10))

        # === KHUNG FILE BROWSER MỚI (THAY THẾ CHỖ GÕ LỆNH) ===
        browser_frame = tk.Frame(content_frame, bg="#FFFFFF", bd=0, highlightbackground="#D1D5DB", highlightthickness=1)
        browser_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        top_browser = tk.Frame(browser_frame, bg="#F9FAFB")
        top_browser.pack(fill=tk.X)
        ttk.Button(top_browser, text="↑ Lên thư mục cha", command=self.go_up_dir).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Label(top_browser, text="Mẹo: Double-Click vào Folder để mở, vào File để tải về", background="#F9FAFB", foreground="#6B7280").pack(side=tk.RIGHT, padx=10, pady=5)

        self.file_tree = ttk.Treeview(browser_frame, columns=("name", "size", "type"), show="headings")
        self.file_tree.heading("name", text="Tên tập tin / Thư mục")
        self.file_tree.heading("size", text="Kích thước (Bytes)")
        self.file_tree.heading("type", text="Loại")
        self.file_tree.column("name", width=300)
        self.file_tree.column("size", width=120, anchor=tk.E)
        self.file_tree.column("type", width=80, anchor=tk.CENTER)
        self.file_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        self.file_tree.bind("<Double-1>", self.on_tree_double_click)

        # Log Terminal thu nhỏ xuống dưới
        log_frame = tk.Frame(content_frame, bg="#1E1E1E", height=120)
        log_frame.pack(fill=tk.X)
        log_frame.pack_propagate(False)
        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', bg="#1E1E1E", fg="#D4D4D4", font=("Consolas", 9), bd=0, padx=10, pady=10)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.tag_config("client", foreground="#4FC1FF")
        self.log_area.tag_config("server", foreground="#B5CEA8")
        
        self.write_log("Khởi tạo Hybrid FTP Client thành công. Sẵn sàng kết nối...", is_client=True)

    def write_log(self, message, is_client=True):
        self.log_area.config(state='normal')
        tag = "client" if is_client else "server"
        prefix = "➜ " if is_client else "✓ "
        if message.startswith("===") or message.startswith("❌") or message.startswith("✅"): prefix = ""
        self.log_area.insert(tk.END, f"{prefix}{message}\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def start_connection(self):
        self.btn_connect.config(state="disabled")
        threading.Thread(target=self._login_flow, args=(self.ip_var.get().strip(), int(self.port_var.get().strip()), self.user_var.get().strip(), self.pass_var.get().strip()), daemon=True).start()

    def _send_cmd(self, sock, command):
        self.write_log(command, is_client=True)
        sock.sendall(f"{command}\r\n".encode('utf-8'))
        response = sock.recv(1024).decode('utf-8').strip()
        self.write_log(response, is_client=False)
        return response

    def _login_flow(self, ip, port, user, password):
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.write_log(f"Đang kết nối đến {ip}:{port}...")
            self.tcp_sock.connect((ip, port))
            self.write_log(self.tcp_sock.recv(1024).decode('utf-8').strip(), is_client=False)
            
            if not self._send_cmd(self.tcp_sock, f"USER {user}").startswith("331"): raise Exception("Server từ chối Username!")
            if self._send_cmd(self.tcp_sock, f"PASS {password}").startswith("230"):
                self.write_log("ĐĂNG NHẬP THÀNH CÔNG! Đang đổ dữ liệu cây thư mục...")
                self.btn_list.config(state="normal")
                self.btn_stor.config(state="normal")
                self.btn_connect.config(text="Đã kết nối")
                
                # TỰ ĐỘNG GỌI LIST SAU KHI LOGIN
                self.root.after(500, self.list_files)
            else:
                raise Exception("Sai mật khẩu hoặc bị từ chối!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể kết nối hoặc đăng nhập:\n{str(e)}")
            self.btn_connect.config(state="normal", text="Kết nối Server")
            if hasattr(self, 'tcp_sock'): self.tcp_sock.close()

    def list_files(self):
        threading.Thread(target=self._list_flow, daemon=True).start()

    def _list_flow(self):
        try:
            is_passive = self.use_pasv_var.get()
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_data_addr = None
            
            if not is_passive:
                data_sock.bind(('0.0.0.0', 0))
                _, client_port = data_sock.getsockname()
                my_lan_ip = self.tcp_sock.getsockname()[0]
                ip_format = my_lan_ip.replace('.', ',')
                res_port = self._send_cmd(self.tcp_sock, f"PORT {ip_format},{client_port//256},{client_port%256}")
                if not res_port.startswith("200"): raise Exception("Server từ chối lệnh PORT!")
            else:
                res_pasv = self._send_cmd(self.tcp_sock, "PASV")
                match = re.search(r'\((\d+,\d+,\d+,\d+,\d+,\d+)\)', res_pasv)
                parts = match.group(1).split(',')
                server_data_addr = (f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}", (int(parts[4])*256)+int(parts[5]))

            if self._send_cmd(self.tcp_sock, "LIST").startswith("150"):
                if is_passive: data_sock.sendto(b"READY", server_data_addr)
                    
                save_name = "client_received_list.txt"
                rdt_receive(data_sock, save_name)
                
                # CẬP NHẬT GIAO DIỆN TREEVIEW TỪ FILE .TXT SERVER GỬI VỀ
                with open(save_name, "r", encoding="utf-8") as f: lines = f.readlines()
                self._update_treeview_ui(lines)
                
                if os.path.exists(save_name): os.remove(save_name)
                self.write_log(self.tcp_sock.recv(1024).decode('utf-8').strip(), is_client=False)
        except Exception as e:
            self.write_log(f"Lỗi lấy danh sách: {e}")
        finally:
            data_sock.close()

    def _update_treeview_ui(self, lines):
        def _refresh():
            # Xóa danh sách cũ
            for item in self.file_tree.get_children(): 
                self.file_tree.delete(item)
                
            folders, files = [], []
            for line in lines:
                if not line.strip(): continue
                
                # Cắt chuỗi tối đa 5 lần để tạo ra đúng 6 phần tử (phần tử cuối là Tên file, giữ nguyên khoảng trắng nếu có)
                parts = line.split(maxsplit=5)
                
                # Kiểm tra đủ 6 phần (Quyền, Links, Owner, Group, Size, Name)
                if len(parts) >= 6:
                    is_dir = parts[0].startswith('d')
                    size = parts[4]
                    name = parts[5].strip()
                    
                    if is_dir: 
                        # Thư mục thì ẩn size
                        folders.append((f"📁 {name}", "", "Folder", name)) 
                    else: 
                        files.append((f"📄 {name}", size, "File", name))
            
            # Đổ dữ liệu vào Treeview (Ưu tiên thư mục hiện trước, file hiện sau)
            for f in folders: self.file_tree.insert("", tk.END, values=f)
            for f in files: self.file_tree.insert("", tk.END, values=f)
            
        # Dùng .after để đảm bảo an toàn luồng (Thread-safe) cho Tkinter
        self.root.after(0, _refresh)

    def on_tree_double_click(self, event):
        item = self.file_tree.selection()
        if not item: return
        values = self.file_tree.item(item[0], "values")
        ftype = values[2]
        real_name = values[3] # Lấy tên không có Icon 📁 / 📄
        
        if ftype == "Folder":
            threading.Thread(target=self._change_dir, args=(real_name,), daemon=True).start()
        elif ftype == "File":
            threading.Thread(target=self._download_flow, args=(real_name,), daemon=True).start()

    def go_up_dir(self):
        if hasattr(self, 'tcp_sock'):
            threading.Thread(target=self._change_dir, args=("..",), daemon=True).start()

    def _change_dir(self, target_folder):
        res = self._send_cmd(self.tcp_sock, f"CWD {target_folder}")
        if res.startswith("250"):
            self.list_files() # Gọi refresh lại Treeview sau khi đổi thư mục thành công

    def upload_file(self):
        filepath = filedialog.askopenfilename(title="Chọn file tải lên Server")
        if filepath: threading.Thread(target=self._upload_flow, args=(filepath,), daemon=True).start()

    def _download_flow(self, filename):
        try:
            is_passive = self.use_pasv_var.get()
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_data_addr = None 
            
            if not is_passive:
                data_sock.bind(('0.0.0.0', 0))
                _, client_port = data_sock.getsockname()
                my_lan_ip = self.tcp_sock.getsockname()[0]
                res_port = self._send_cmd(self.tcp_sock, f"PORT {my_lan_ip.replace('.', ',')},{client_port//256},{client_port%256}")
                if not res_port.startswith("200"): raise Exception("Server từ chối PORT!")
            else:
                res_pasv = self._send_cmd(self.tcp_sock, "PASV")
                match = re.search(r'\((\d+,\d+,\d+,\d+,\d+,\d+)\)', res_pasv)
                parts = match.group(1).split(',')
                server_data_addr = (f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}", (int(parts[4])*256)+int(parts[5]))

            if self._send_cmd(self.tcp_sock, f"RETR {filename}").startswith("150"):
                if is_passive: data_sock.sendto(b"READY", server_data_addr)
                
                save_path = f"downloaded_{filename}" 
                rdt_receive(data_sock, save_path, self.client_data_type)
                self.write_log(self.tcp_sock.recv(1024).decode('utf-8').strip(), is_client=False)
                self.write_log(f"Đã lưu file: {save_path}")
        except Exception as e: self.write_log(f"Lỗi tải về: {e}")
        finally: data_sock.close()

    def _upload_flow(self, filepath):
        try:
            filename = os.path.basename(filepath)
            is_passive = self.use_pasv_var.get()
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_data_addr = None 
            
            if not is_passive:
                data_sock.bind(('0.0.0.0', 0))
                _, client_port = data_sock.getsockname()
                my_lan_ip = self.tcp_sock.getsockname()[0]
                res_port = self._send_cmd(self.tcp_sock, f"PORT {my_lan_ip.replace('.', ',')},{client_port//256},{client_port%256}")
                if not res_port.startswith("200"): raise Exception("Từ chối PORT!")
            else:
                res_pasv = self._send_cmd(self.tcp_sock, "PASV")
                match = re.search(r'\((\d+,\d+,\d+,\d+,\d+,\d+)\)', res_pasv)
                parts = match.group(1).split(',')
                server_data_addr = (f"{parts[0]}.{parts[1]}.{parts[2]}.{parts[3]}", (int(parts[4])*256)+int(parts[5]))

            if self._send_cmd(self.tcp_sock, f"STOR {filename}").startswith("150"):
                if not is_passive:
                    data_sock.settimeout(5.0)
                    _, s_addr = data_sock.recvfrom(1024)
                    server_data_addr = s_addr
                
                rdt_send(filepath, server_data_addr, self.client_data_type)
                self.write_log(self.tcp_sock.recv(1024).decode('utf-8').strip(), is_client=False)
                self.write_log(f"Upload hoàn tất: {filename}")
                self.list_files() # XONG UPLOAD -> ÉP LÀM MỚI DANH SÁCH FILE NGAY
        except Exception as e: self.write_log(f"Lỗi Upload: {e}")
        finally: data_sock.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPClientGUI(root)
    root.mainloop()