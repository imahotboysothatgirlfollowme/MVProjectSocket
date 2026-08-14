import os
import socket
import hashlib
from rdt_core import rdt_send, rdt_receive

def get_safe_path(server_root, current_dir, requested_path):
    safe_requested = requested_path.lstrip('/\\')
    target_path = os.path.abspath(os.path.join(current_dir, safe_requested))
    if os.path.commonpath([server_root, target_path]) == server_root:
        return target_path
    return None

class FTPCommandProcessor:
    def __init__(self, conn, addr, server_root, active_clients, write_log, update_dashboard):
        self.conn = conn
        self.addr = addr
        self.server_root = server_root
        self.active_clients = active_clients
        self.write_log = write_log
        self.update_dashboard = update_dashboard
        
        self.is_logged_in = False
        self.client_udp_addr = None
        self.is_passive = False
        self.pasv_sock = None
        self.temp_user = ""

    def update_speed(self, speed_str):
        if self.addr in self.active_clients:
            self.active_clients[self.addr]["speed"] = speed_str

    def process(self, data):
        parts = data.split(' ', 1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "USER":
            self.temp_user = arg
            self.conn.sendall(b"331 Username OK, can Password\r\n")
            
        elif cmd == "PASS":
            if arg == "123456":
                self.is_logged_in = True
                self.active_clients[self.addr]["user"] = self.temp_user
                self.active_clients[self.addr]["status"] = "Đã đăng nhập"
                self.conn.sendall(b"230 Dang nhap thanh cong\r\n")
                self.update_dashboard()
            else:
                self.conn.sendall(b"530 Sai mat khau\r\n")
                
        elif cmd == "QUIT":
            self.conn.sendall(b"221 Tam biet!\r\n")
            return False 
        
        elif not self.is_logged_in:
            self.conn.sendall(b"530 Ban chua dang nhap\r\n")
        
        elif cmd == "PORT":
            try:
                p = arg.split(',')
                ip = f"{int(p[0])}.{int(p[1])}.{int(p[2])}.{int(p[3])}"
                udp_port = (int(p[4]) * 256) + int(p[5])
                
                self.client_udp_addr = (ip, udp_port)
                self.is_passive = False
                self.active_clients[self.addr]["mode"] = "ACTIVE"
                self.update_dashboard()
                self.conn.sendall(b"200 PORT ghi nhan thanh cong\r\n")
            except Exception:
                self.conn.sendall(b"501 Syntax error in parameters\r\n")
                
        elif cmd == "PASV":
            self.pasv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.pasv_sock.bind(('0.0.0.0', 0))
            _, server_port = self.pasv_sock.getsockname()
            
            my_lan_ip = self.conn.getsockname()[0]
            ip_pasv = my_lan_ip.replace('.', ',')
            p1, p2 = server_port // 256, server_port % 256
            
            self.conn.sendall(f"227 Entering Passive Mode ({ip_pasv},{p1},{p2})\r\n".encode('utf-8'))
            self.is_passive = True
            self.active_clients[self.addr]["mode"] = "PASSIVE"
            self.update_dashboard()
            
        elif cmd == "RETR":
            current_type = self.active_clients[self.addr]["data_type"]
            if not self.client_udp_addr and not self.is_passive:
                self.conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                return True

            target_file = get_safe_path(self.server_root, self.active_clients[self.addr]["current_dir"], arg)
            if target_file and os.path.isfile(target_file):
                self.conn.sendall(b"150 File ton tai, dang mo luong UDP...\r\n")
                self.active_clients[self.addr]["status"] = f"Đang gửi: {arg[:15]}"
                self.update_dashboard()
                
                if self.is_passive and self.pasv_sock:
                    try:
                        self.pasv_sock.settimeout(5.0)
                        _, c_addr = self.pasv_sock.recvfrom(1024)
                        self.client_udp_addr = c_addr 
                        self.pasv_sock.close() 
                        self.pasv_sock = None
                    except socket.timeout:
                        self.conn.sendall(b"426 Loi Timeout\r\n")
                        self.active_clients[self.addr]["status"] = "Lỗi timeout"
                        self.active_clients[self.addr]["speed"] = "-"
                        self.update_dashboard()
                        return True
                
                rdt_send(target_file, self.client_udp_addr, current_type, speed_cb=self.update_speed)
                self.conn.sendall(b"226 Truyen file hoan tat\r\n")
                
                self.active_clients[self.addr]["status"] = "Rảnh rỗi"
                self.active_clients[self.addr]["speed"] = "-"
                self.update_dashboard()
                self.client_udp_addr = None 
                self.is_passive = False
            else:
                self.conn.sendall(b"550 Khong tim thay file\r\n")

        elif cmd == "STOR":
            current_type = self.active_clients[self.addr]["data_type"]
            if not self.client_udp_addr and not self.is_passive:
                self.conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                return True
            
            safe_filename = os.path.basename(arg)
            save_path = get_safe_path(self.server_root, self.active_clients[self.addr]["current_dir"], f"server_recv_{safe_filename}")
            if not save_path:
                self.conn.sendall(b"553 Ten file khong hop le\r\n")
                return True
            
            self.conn.sendall(b"150 San sang nhan file...\r\n")
            self.active_clients[self.addr]["status"] = f"Đang nhận: {safe_filename[:15]}"
            self.update_dashboard()
            
            if not self.is_passive:
                temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                temp_sock.sendto(b"READY", self.client_udp_addr)
                rdt_receive(temp_sock, save_path, current_type, speed_cb=self.update_speed)
                temp_sock.close()
            else:
                rdt_receive(self.pasv_sock, save_path, current_type, speed_cb=self.update_speed)
                self.pasv_sock.close()
                self.pasv_sock = None
            
            self.conn.sendall(b"226 Truyen file hoan tat\r\n")
            self.active_clients[self.addr]["status"] = "Rảnh rỗi"
            self.active_clients[self.addr]["speed"] = "-"
            self.update_dashboard()
            self.client_udp_addr = None 
            self.is_passive = False

        elif cmd == "LIST":
            if not self.client_udp_addr and not self.is_passive:
                self.conn.sendall(b"425 Vui long gui lenh PORT hoac PASV truoc\r\n")
                return True
            
            self.conn.sendall(b"150 Bat dau gui danh sach file...\r\n")
            self.active_clients[self.addr]["status"] = "Đang lấy danh sách"
            self.update_dashboard()
            
            listing = ""
            client_dir = self.active_clients[self.addr]["current_dir"]
            for f in os.listdir(client_dir):
                full_path = os.path.join(client_dir, f)
                if os.path.isfile(full_path):
                    size = os.path.getsize(full_path)
                    listing += f"-rwxr-xr-x 1 owner group {size:8} {f}\r\r\n"
                elif os.path.isdir(full_path):
                    listing += f"drwxr-xr-x 1 owner group        0 {f}\r\r\n"

            temp_filename = "temp_server_list.txt"
            with open(temp_filename, "w", encoding="utf-8") as tf: tf.write(listing)
            
            if self.is_passive and self.pasv_sock:
                try:
                    self.pasv_sock.settimeout(5.0)
                    _, c_addr = self.pasv_sock.recvfrom(1024)
                    self.client_udp_addr = c_addr
                    self.pasv_sock.close()
                    self.pasv_sock = None
                except socket.timeout:
                    pass
            
            rdt_send(temp_filename, self.client_udp_addr, speed_cb=self.update_speed)
            if os.path.exists(temp_filename): os.remove(temp_filename)
            
            self.conn.sendall(b"226 Truyen danh sach hoan tat\r\n")
            self.active_clients[self.addr]["status"] = "Rảnh rỗi"
            self.update_dashboard()
            self.client_udp_addr = None
            self.is_passive = False

        elif cmd == "HASH":
            target_file = get_safe_path(self.server_root, self.active_clients[self.addr]["current_dir"], arg)
            if target_file and os.path.isfile(target_file):
                hasher = hashlib.sha256()
                with open(target_file, "rb") as f: hasher.update(f.read())
                self.conn.sendall(f"200 {hasher.hexdigest()}\r\n".encode('utf-8'))
            else:
                self.conn.sendall(b"550 Khong tim thay file\r\n")
                
        elif cmd == "TYPE":
            if arg.upper() in ['A', 'I']:
                self.active_clients[self.addr]["data_type"] = arg.upper()
                self.conn.sendall(f"200 TYPE {arg.upper()}\r\n".encode('utf-8'))
            else:
                self.conn.sendall(b"501 TYPE (A hoac I)\r\n")
                
        elif cmd == "PWD":
            client_dir = self.active_clients[self.addr]["current_dir"]
            self.conn.sendall(f"257 \"{client_dir}\" is current directory\r\n".encode('utf-8'))
            
        elif cmd == "CWD":
            target_dir = get_safe_path(self.server_root, self.active_clients[self.addr]["current_dir"], arg)
            if target_dir and os.path.isdir(target_dir):
                self.active_clients[self.addr]["current_dir"] = target_dir
                self.conn.sendall(b"250 CWD OK\r\n")
            else:
                self.conn.sendall(b"550 Loi duong dan\r\n")
                
        elif cmd == "CDUP":
            target_dir = get_safe_path(self.server_root, self.active_clients[self.addr]["current_dir"], "..")
            if target_dir:
                self.active_clients[self.addr]["current_dir"] = target_dir
                self.conn.sendall(b"250 CDUP OK\r\n")
            else:
                self.conn.sendall(b"550 Khong the lui\r\n")
        else:
            self.conn.sendall(b"502 Lenh chua ho tro\r\n")
        return True