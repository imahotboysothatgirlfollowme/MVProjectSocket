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
        self.root.title("Hybrid FTP Client")
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

        # === THÊM MỚI: Nút HASH đặt cạnh nút Upload ===
        self.btn_hash = ttk.Button(btn_container, text="🔍 Kiểm tra Hash", style="Action.TButton", state="disabled", command=self.on_hash_button_click)
        self.btn_hash.grid(row=0, column=2, padx=(0, 10))

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

        # === THÊM MỚI: Bắt sự kiện click chọn dòng để bật/tắt nút HASH ===
        self.file_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # THÊM MỚI: Khởi tạo Menu chuột phải
        self.file_tree.bind("<Button-3>", self.show_context_menu)
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Kiểm tra mã băm (SHA-256)", command=self.check_server_hash)

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
        # Bọc logic cập nhật UI vào một hàm con
        def _append_log():
            self.log_area.config(state='normal')
            tag = "client" if is_client else "server"
            prefix = "➜ " if is_client else "✓ "
            if message.startswith("===") or message.startswith("❌") or message.startswith("✅"): 
                prefix = ""
            self.log_area.insert(tk.END, f"{prefix}{message}\n", tag)
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')
            
        # Đẩy hàm con này cho luồng chính (Main Thread) của Tkinter xử lý
        self.root.after(0, _append_log)

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
        login_success = False 
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Các hàm phụ trợ để luồng chính xử lý UI an toàn
        def _ui_login_success():
            self.btn_list.config(state="normal")
            self.btn_stor.config(state="normal")
            self.btn_connect.config(text="Đã kết nối")
            
        def _ui_login_error(title, msg):
            messagebox.showerror(title, msg)
            self.btn_connect.config(state="normal", text="Kết nối Server")

        try:
            self.write_log(f"Đang kết nối đến {ip}:{port}...")
            self.tcp_sock.connect((ip, port))
            self.write_log(self.tcp_sock.recv(1024).decode('utf-8').strip(), is_client=False)
            
            if not self._send_cmd(self.tcp_sock, f"USER {user}").startswith("331"): 
                raise Exception("Server từ chối Username!")
                
            if self._send_cmd(self.tcp_sock, f"PASS {password}").startswith("230"):
                self.write_log("ĐĂNG NHẬP THÀNH CÔNG! Đang đổ dữ liệu cây thư mục...")
                
                # Báo luồng chính cập nhật nút bấm
                self.root.after(0, _ui_login_success)
                
                login_success = True 
                
                self.root.after(500, self.list_files)
            else:
                raise Exception("Sai mật khẩu hoặc bị từ chối!")
                
        except ConnectionRefusedError:
            self.root.after(0, lambda: _ui_login_error("Lỗi Kết Nối", "Server từ chối kết nối. Hãy kiểm tra lại IP/Port hoặc đảm bảo Server đang mở."))
        except TimeoutError:
            self.root.after(0, lambda: _ui_login_error("Lỗi Mạng", "Kết nối quá hạn (Timeout). Server không phản hồi."))
        except Exception as e:
            self.root.after(0, lambda: _ui_login_error("Lỗi", f"Không thể kết nối hoặc đăng nhập:\n{str(e)}"))
        finally:
            if not login_success and hasattr(self, 'tcp_sock'): 
                self.tcp_sock.close()

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
        # Thay vì except Exception as e: ...
        except ConnectionResetError:
            self.write_log("Lỗi Mạng: Giao tiếp TCP bị Server ngắt đột ngột.", is_client=True)
        except socket.timeout:
            self.write_log("Lỗi Mạng: Quá thời gian chờ luồng UDP.", is_client=True)
        except OSError as e:
            self.write_log(f"Lỗi File/Đường dẫn: Hệ điều hành từ chối thao tác file ({e})", is_client=True)
        except Exception as e:
            self.write_log(f"Lỗi không xác định khi tải về: {e}", is_client=True)
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

    def on_tree_select(self, event):
        """Hàm này tự động chạy khi người dùng bấm vào 1 dòng trên giao diện"""
        selection = self.file_tree.selection()
        if selection:
            # Lấy thông tin dòng đang được chọn
            values = self.file_tree.item(selection[0], "values")
            # values[2] lưu loại ("File" hoặc "Folder")
            if values[2] == "File":
                # Nếu là File -> Cho phép bấm nút
                self.btn_hash.config(state="normal")
            else:
                # Nếu là Folder -> Làm mờ nút
                self.btn_hash.config(state="disabled")
        else:
            self.btn_hash.config(state="disabled")

    def on_hash_button_click(self):
        """Xử lý khi người dùng bấm vào nút Kiểm tra Hash"""
        selection = self.file_tree.selection()
        if not selection: return
        
        # values[3] chứa tên file thật trên Server (không có icon)
        server_filename = self.file_tree.item(selection[0], "values")[3] 
        
        # BƯỚC 1: Mở hộp thoại chọn file từ máy tính (Bắt buộc chạy trên luồng chính của UI)
        local_filepath = filedialog.askopenfilename(
            title=f"Chọn file dưới máy tính để so sánh với '{server_filename}'"
        )
        
        if local_filepath: # Nếu người dùng chọn file (không bấm Cancel)
            # BƯỚC 2: Khởi chạy luồng phụ để tính toán Hash và gọi mạng (Giúp UI không bị đơ)
            threading.Thread(
                target=self._compare_hash_flow, 
                args=(server_filename, local_filepath), 
                daemon=True
            ).start()

    def _compare_hash_flow(self, server_filename, local_filepath):
        """Luồng chạy ngầm để tính toán và đối chiếu mã băm"""
        try:
            local_name = os.path.basename(local_filepath)
            self.write_log(f"Đang tính mã băm SHA-256 cho file local: {local_name}...")
            
            # Tính mã băm local (Đọc từng chunk 4KB để không làm tràn RAM nếu file nặng vài GB)
            hasher = hashlib.sha256()
            with open(local_filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            local_hash = hasher.hexdigest()
            
            # Gọi Server để lấy mã băm
            self.write_log(f"Đang yêu cầu mã băm từ Server cho file: {server_filename}...")
            res = self._send_cmd(self.tcp_sock, f"HASH {server_filename}")
            
            if res.startswith("200"):
                server_hash = res.split(" ", 1)[1]
                
                # So sánh và báo cáo (Dùng root.after để gọi hộp thoại an toàn trên Main Thread)
                def show_result():
                    if local_hash == server_hash:
                        messagebox.showinfo(
                            "✅ Khớp hoàn toàn", 
                            f"Mã băm SHA-256 trùng khớp 100%!\n\n"
                            f"File Server: {server_filename}\n"
                            f"File Local : {local_name}\n\n"
                            f"Hash: {server_hash}"
                        )
                        self.write_log("Kết quả HASH: Khớp 100%. File đảm bảo toàn vẹn tuyệt đối.")
                    else:
                        messagebox.showwarning(
                            "❌ Lệch mã băm", 
                            f"CẢNH BÁO: Mã băm không khớp! Dữ liệu có thể đã bị sửa đổi hoặc lỗi.\n\n"
                            f"Server Hash: {server_hash}\n"
                            f"Local Hash : {local_hash}"
                        )
                        self.write_log("Kết quả HASH: Cảnh báo lệch mã băm!")
                        
                self.root.after(0, show_result)
            else:
                self.root.after(0, lambda: messagebox.showerror("Lỗi", "Server từ chối tính mã băm hoặc file không tồn tại."))
                
        except Exception as e:
            self.write_log(f"Lỗi khi so sánh HASH: {e}")
            self.root.after(0, lambda: messagebox.showerror("Lỗi hệ thống", f"Không thể hoàn tất kiểm tra HASH:\n{str(e)}"))

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

                # === BẮT ĐẦU PHẦN CODE AUTO-VERIFY THÊM VÀO ===
                self.write_log("Đang kiểm tra tính toàn vẹn của file tải về...")
                hash_res = self._send_cmd(self.tcp_sock, f"HASH {filename}")
                if hash_res.startswith("200"):
                    server_hash = hash_res.split(" ", 1)[1]
                    
                    # Tự tính mã băm file local vừa tải về
                    hasher = hashlib.sha256()
                    with open(save_path, "rb") as f:
                        hasher.update(f.read())
                    local_hash = hasher.hexdigest()
                    
                    if server_hash == local_hash:
                        self.write_log("TẢI THÀNH CÔNG: Mã băm SHA-256 khớp 100%. File toàn vẹn.")
                    else:
                        self.write_log(f"CẢNH BÁO: File bị hỏng!\n- Server: {server_hash[:15]}...\n- Client: {local_hash[:15]}...")
                # === KẾT THÚC PHẦN AUTO-VERIFY ===
        # Thay vì except Exception as e: ...
        except ConnectionResetError:
            self.write_log("Lỗi Mạng: Giao tiếp TCP bị Server ngắt đột ngột.", is_client=True)
        except socket.timeout:
            self.write_log("Lỗi Mạng: Quá thời gian chờ luồng UDP.", is_client=True)
        except OSError as e:
            self.write_log(f"Lỗi File/Đường dẫn: Hệ điều hành từ chối thao tác file ({e})", is_client=True)
        except Exception as e:
            self.write_log(f"Lỗi không xác định khi tải về: {e}", is_client=True)
        finally:
            data_sock.close()

    def show_context_menu(self, event):
        item = self.file_tree.identify_row(event.y)
        if item:
            self.file_tree.selection_set(item)
            values = self.file_tree.item(item, "values")
            # Chỉ hiện Menu nếu click vào File, bỏ qua Folder
            if values[2] == "File": 
                self.context_menu.tk_popup(event.x_root, event.y_root)

    def check_server_hash(self):
        item = self.file_tree.selection()
        if not item: return
        # Lấy tên file thực tế
        filename = self.file_tree.item(item[0], "values")[3] 
        threading.Thread(target=self._hash_flow, args=(filename,), daemon=True).start()

    def _hash_flow(self, filename):
        try:
            self.write_log(f"Đang yêu cầu Server tính mã SHA-256 cho: {filename}...")
            res = self._send_cmd(self.tcp_sock, f"HASH {filename}")
            
            if res.startswith("200"):
                server_hash = res.split(" ", 1)[1]
                # Dùng luồng chính để hiển thị UI an toàn
                self.root.after(0, lambda: messagebox.showinfo(
                    "Mã băm SHA-256", 
                    f"Tên file: {filename}\n\nSHA-256 (Trên Server):\n{server_hash}"
                ))
            else:
                self.root.after(0, lambda: messagebox.showerror("Lỗi", "Server từ chối tính mã băm."))
        except Exception as e:
            self.write_log(f"Lỗi khi yêu cầu HASH: {e}")

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
        # Thay vì except Exception as e: ...
        except ConnectionResetError:
            self.write_log("Lỗi Mạng: Giao tiếp TCP bị Server ngắt đột ngột.", is_client=True)
        except socket.timeout:
            self.write_log("Lỗi Mạng: Quá thời gian chờ luồng UDP.", is_client=True)
        except OSError as e:
            self.write_log(f"Lỗi File/Đường dẫn: Hệ điều hành từ chối thao tác file ({e})", is_client=True)
        except Exception as e:
            self.write_log(f"Lỗi không xác định khi tải về: {e}", is_client=True)
        finally:
            data_sock.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = FTPClientGUI(root)
    root.mainloop()