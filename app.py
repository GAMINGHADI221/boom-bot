import os, sys, time, json, ssl, socket, threading, asyncio, random
from datetime import datetime
from threading import Thread
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
from functools import wraps
import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from google.protobuf.timestamp_pb2 import Timestamp
# আপনার কাস্টম মডিউল (একই ফোল্ডারে থাকতে হবে)
from byte import *
from byte import xSEndMsg, Auth_Chat
from xHeaders import *
from black9 import openroom, spmroom
import xKEys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== গ্লোবাল ====================
connected_clients = {}
connected_clients_lock = threading.Lock()
active_spam_targets = {}       # {uid: start_time}
spam_running = False
spam_thread = None
targets = []                   # inv_uid.txt থেকে লোড
app = Flask(__name__)
C = "\033[96m"; G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; RS = "\033[0m"; BOLD = "\033[1m"
_ID = '4575104506'
_PW = 'TORIKUL_TORIKUL_E6H3H'

# ==================== ব্যাজ ভ্যালু ====================
BADGES = {
    "V_BADGE": 32768,
    "PRO_BADGE": 262144,
    "CRAFTLAND": 1048576,
    "MODERATOR": 2048,
    "SMALL_V": 64,
}
GROUP_CONFIGS = {3: {"type": 1}, 5: {"type": 2}, 6: {"type": 3}}

# ==================== ফাইল লোডার ====================
def load_targets(filename="inv_uid.txt"):
    global targets
    uids = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                uid = line.strip()
                if uid and not uid.startswith("#") and uid.isdigit():
                    uids.append(uid)
        targets = uids
        print(f"{G}📦 Loaded {len(targets)} targets from {filename}{RS}")
    except FileNotFoundError:
        print(f"{Y}⚠️ {filename} not found, creating...{RS}")
        with open(filename, "w") as f:
            f.write("# Target UIDs, one per line\n")
        targets = []
    return targets
load_targets("inv_uid.txt")

def save_targets(uids, filename="inv_uid.txt"):
    global targets
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# Target UIDs, one per line\n")
            for uid in uids:
                f.write(f"{uid}\n")
        targets = uids
        print(f"{G}💾 Saved {len(uids)} targets to {filename}{RS}")
    except Exception as e:
        print(f"{R}❌ Save error: {e}{RS}")

# ==================== প্যাকেট ক্রিয়েটর ====================
def create_proto_sync(fields):
    packet = bytearray()
    for field, value in fields.items():
        field_num = int(field)
        if isinstance(value, dict):
            nested = create_proto_sync(value)
            packet.extend(encode_varint_sync((field_num << 3) | 2))
            packet.extend(encode_varint_sync(len(nested)))
            packet.extend(nested)
        elif isinstance(value, int):
            packet.extend(encode_varint_sync((field_num << 3) | 0))
            packet.extend(encode_varint_sync(value))
        elif isinstance(value, str):
            data = value.encode('utf-8')
            packet.extend(encode_varint_sync((field_num << 3) | 2))
            packet.extend(encode_varint_sync(len(data)))
            packet.extend(data)
        elif isinstance(value, bytes):
            packet.extend(encode_varint_sync((field_num << 3) | 2))
            packet.extend(encode_varint_sync(len(value)))
            packet.extend(value)
    return bytes(packet)

def encode_varint_sync(value: int) -> bytes:
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        result.append(byte)
        if not value:
            break
    return bytes(result)

def create_badge_invite_packet(key, iv, target_uid, badge_value, players=5, region="BD"):
    """ইনভাইট + ব্যাজ (যা কাজ করে)"""
    try:
        proto_fields = {
            1: 2,
            2: {
                1: int(target_uid),
                2: region.upper(),
                4: players,
                31: {1: 1, 2: badge_value},
                32: badge_value
            }
        }
        packet = create_proto_sync(proto_fields).hex()
        if region.lower() == "ind": packet_type = "0514"
        elif region.lower() == "bd": packet_type = "0519"
        else: packet_type = "0515"
        encrypted = EnC_PacKeT(packet, key, iv)
        length = len(encrypted) // 2
        len_hex = DecodE_HeX(length)
        padding_map = {2: "000000", 3: "00000", 4: "0000", 5: "000"}
        padding = padding_map.get(len(len_hex), "000")
        return bytes.fromhex(packet_type + padding + len_hex + encrypted)
    except Exception as e:
        print(f"{R}❌ Badge invite packet error: {e}{RS}")
        return None

def create_group_invite_packet(key, iv, target_uid, players=5, region="BD"):
    """সাধারণ ইনভাইট (৩/৫/৬)"""
    try:
        group_type = GROUP_CONFIGS[players]["type"]
        proto_fields = {
            1: 2,
            2: {
                1: int(target_uid),
                2: region.upper(),
                4: players,
                # ৩১ ও ৩২ না দিলে শুধু ইনভাইট
            }
        }
        packet = create_proto_sync(proto_fields).hex()
        if region.lower() == "ind": packet_type = "0514"
        elif region.lower() == "bd": packet_type = "0519"
        else: packet_type = "0515"
        encrypted = EnC_PacKeT(packet, key, iv)
        length = len(encrypted) // 2
        len_hex = DecodE_HeX(length)
        padding_map = {2: "000000", 3: "00000", 4: "0000", 5: "000"}
        padding = padding_map.get(len(len_hex), "000")
        return bytes.fromhex(packet_type + padding + len_hex + encrypted)
    except Exception as e:
        print(f"{R}❌ Group invite packet error: {e}{RS}")
        return None

# ==================== স্প্যাম ওয়ার্কার ====================
def spam_worker():
    global spam_running, active_spam_targets
    print(f"\n{G}🚀 SPAM WORKER STARTED{RS}")
    total_requests = 0
    round_num = 0
    last_keepalive = time.time()

    def run_async(coro):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        except:
            return None
        finally:
            loop.close()

    while spam_running:
        with connected_clients_lock:
            # মৃত ক্লায়েন্ট বাদ দিন
            active_clients = []
            for cid, client in list(connected_clients.items()):
                try:
                    if client.CliEnts2 and client.CliEnts2.fileno() != -1:
                        active_clients.append(client)
                    else:
                        del connected_clients[cid]
                except:
                    del connected_clients[cid]
            clients = active_clients

        if not clients:
            time.sleep(2)
            continue

        # কিপ-অ্যালাইভ (openroom) – প্রতি ২৫ সেকেন্ডে
        if time.time() - last_keepalive > 25:
            for client in clients:
                try:
                    pkt = openroom(client.key, client.iv)
                    if pkt:
                        client.CliEnts2.send(pkt)
                except:
                    pass
            last_keepalive = time.time()

        # বর্তমান টার্গেট লোড (ফাইল থেকে পড়া, যাতে রানটাইমে পরিবর্তন হয়)
        current_targets = targets[:]  # কপি

        if not current_targets:
            time.sleep(5)
            continue

        round_num += 1
        for target in current_targets:
            for client in clients:
                try:
                    if hasattr(client, 'CliEnts2') and client.key:
                        # 1. ব্যাজ ইনভাইট (৫ প্লেয়ার) – সব ব্যাজ পাঠাবে
                        for badge_name, badge_val in BADGES.items():
                            pkt = create_badge_invite_packet(client.key, client.iv, target, badge_val, players=5)
                            if pkt:
                                client.CliEnts2.send(pkt)
                                total_requests += 1
                                time.sleep(0.08)  # ধীর গতি

                        # 2. সাধারণ ইনভাইট (৩, ৫, ৬) – যদি চান
                        for players in [3, 5, 6]:
                            pkt = create_group_invite_packet(client.key, client.iv, target, players=players)
                            if pkt:
                                client.CliEnts2.send(pkt)
                                total_requests += 1
                                time.sleep(0.08)

                        # 3. রুম স্প্যাম (ঐচ্ছিক)
                        try:
                            open_pkt = openroom(client.key, client.iv)
                            if open_pkt:
                                client.CliEnts2.send(open_pkt)
                            spam_pkt = spmroom(client.key, client.iv, target)
                            if spam_pkt:
                                client.CliEnts2.send(spam_pkt)
                                total_requests += 1
                        except:
                            pass

                except Exception as e:
                    print(f"{R}❌ Send error to {target}: {e}{RS}")
                    # এই ক্লায়েন্ট মৃত – বাদ দিন
                    with connected_clients_lock:
                        if client.id in connected_clients:
                            del connected_clients[client.id]
                time.sleep(0.05)

        if round_num % 5 == 0:
            print(f"{C}📊 Round {round_num} | Total req: {total_requests} | Targets: {len(current_targets)} | Bots: {len(clients)}{RS}")

        time.sleep(0.5)

    print(f"{R}🛑 SPAM WORKER STOPPED{RS}")

# ==================== অ্যাকাউন্ট ম্যানেজার ====================
ACCOUNTS = []
def load_accounts(filename="accs.txt"):
    global ACCOUNTS
    loaded = []
    try:
        if not os.path.exists(filename):
            with open(filename, "w") as f:
                f.write("# UID:PASSWORD\n")
            return []
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if ":" in line:
                        uid, pwd = line.split(":", 1)
                    else:
                        uid, pwd = line, ""
                    if uid.isdigit():
                        loaded.append({'id': uid, 'password': pwd})
        print(f"{G}📦 Loaded {len(loaded)} accounts from {filename}{RS}")
    except Exception as e:
        print(f"{R}❌ Error loading accounts: {e}{RS}")
    ACCOUNTS = loaded
    return ACCOUNTS
load_accounts("accs.txt")

# ==================== FF CLIENT (সংক্ষিপ্ত) ====================
class FF_CLient():
    def __init__(self, id, password):
        self.id = id
        self.password = password
        self.key = None
        self.iv = None
        self.Get_FiNal_ToKen_0115()

    def Connect_SerVer_OnLine(self, Token, tok, host, port, key, iv, host2, port2):
        try:
            self.AutH_ToKen_0115 = tok
            self.CliEnts2 = socket.create_connection((host2, int(port2)))
            self.CliEnts2.send(bytes.fromhex(self.AutH_ToKen_0115))
            with connected_clients_lock:
                if self.id not in connected_clients:
                    connected_clients[self.id] = self
                    print(f"{G}✅ Online: {self.id} (Total: {len(connected_clients)}){RS}")
        except Exception as e:
            print(f"{R}❌ Online error {self.id}: {e}{RS}")
            return
        while True:
            try:
                self.DaTa2 = self.CliEnts2.recv(99999)
                if '0500' in self.DaTa2.hex()[0:4] and len(self.DaTa2.hex()) > 30:
                    self.packet = json.loads(DeCode_PackEt(f'08{self.DaTa2.hex().split("08", 1)[1]}'))
                    self.AutH = self.packet['5']['data']['7']['data']
            except: pass

    def Connect_SerVer(self, Token, tok, host, port, key, iv, host2, port2):
        self.AutH_ToKen_0115 = tok
        self.CliEnts = socket.create_connection((host, int(port)))
        self.CliEnts.send(bytes.fromhex(self.AutH_ToKen_0115))
        self.DaTa = self.CliEnts.recv(1024)
        threading.Thread(target=self.Connect_SerVer_OnLine, args=(Token, tok, host, port, key, iv, host2, port2)).start()
        self.key = key
        self.iv = iv
        with connected_clients_lock:
            if self.id not in connected_clients:
                connected_clients[self.id] = self
                print(f"{G}✅ Registered: {self.id}{RS}")
        while True:
            try:
                self.DaTa = self.CliEnts.recv(1024)
                if len(self.DaTa) == 0 or (hasattr(self, 'DaTa2') and len(self.DaTa2) == 0):
                    try:
                        self.CliEnts.close()
                        if hasattr(self, 'CliEnts2'): self.CliEnts2.close()
                        self.Connect_SerVer(Token, tok, host, port, key, iv, host2, port2)
                    except:
                        try:
                            self.CliEnts.close()
                            if hasattr(self, 'CliEnts2'): self.CliEnts2.close()
                            self.Connect_SerVer(Token, tok, host, port, key, iv, host2, port2)
                        except:
                            self.CliEnts.close()
                            if hasattr(self, 'CliEnts2'): self.CliEnts2.close()
                            ResTarT_BoT()
            except Exception as e:
                print(f"{R}❌ Connection error {self.id}: {e}{RS}")
                with connected_clients_lock:
                    if self.id in connected_clients: del connected_clients[self.id]
                self.Connect_SerVer(Token, tok, host, port, key, iv, host2, port2)

    def GeT_Key_Iv(self, serialized_data):
        my_message = xKEys.MyMessage()
        my_message.ParseFromString(serialized_data)
        timestamp, key, iv = my_message.field21, my_message.field22, my_message.field23
        timestamp_obj = Timestamp()
        timestamp_obj.FromNanoseconds(timestamp)
        timestamp_seconds = timestamp_obj.seconds
        timestamp_nanos = timestamp_obj.nanos
        combined_timestamp = timestamp_seconds * 1_000_000_000 + timestamp_nanos
        return combined_timestamp, key, iv

    def Guest_GeneRaTe(self, uid, password):
        self.url = "https://100067.connect.garena.com/oauth/guest/token/grant"
        self.headers = {
            "Host": "100067.connect.garena.com",
            "User-Agent": "GarenaMSDK/4.0.19P4(G011A ;Android 9;en;US;)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "close",
        }
        self.dataa = {
            "uid": f"{uid}",
            "password": f"{password}",
            "response_type": "token",
            "client_type": "2",
            "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
            "client_id": "100067",
        }
        try:
            self.response = requests.post(self.url, headers=self.headers, data=self.dataa).json()
            self.Access_ToKen, self.Access_Uid = self.response['access_token'], self.response['open_id']
            time.sleep(0.2)
            print(f'{C}🔐 Login: {self.id}{RS}')
            return self.ToKen_GeneRaTe(self.Access_ToKen, self.Access_Uid)
        except Exception as e:
            print(f"{R}❌ Login error {self.id}: {e}{RS}")
            time.sleep(10)
            return self.Guest_GeneRaTe(uid, password)

    def GeT_LoGin_PorTs(self, JwT_ToKen, PayLoad, dynamic_url="https://clientbp.ggpolarbear.com"):
        self.UrL = f'{dynamic_url}/GetLoginData'
        self.HeadErs = {
            'Expect': '100-continue',
            'Authorization': f'Bearer {JwT_ToKen}',
            'X-Unity-Version': '2022.3.47f1',
            'X-GA': 'v1 1',
            'ReleaseVersion': 'OB54',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
            'Connection': 'close',
            'Accept-Encoding': 'deflate, gzip',
        }
        try:
            self.Res = requests.post(self.UrL, headers=self.HeadErs, data=PayLoad, verify=False)
            self.BesTo_data = json.loads(DeCode_PackEt(self.Res.content.hex()))
            address, address2 = self.BesTo_data['32']['data'], self.BesTo_data['14']['data']
            ip, ip2 = address[:len(address) - 6], address2[:len(address2) - 6]
            port, port2 = address[len(address) - 5:], address2[len(address2) - 5:]
            return ip, port, ip2, port2
        except Exception as e:
            print(f"{R}❌ Failed to get ports: {e}{RS}")
        return None, None, None, None

    def ToKen_GeneRaTe(self, Access_ToKen, Access_Uid):
        self.UrL = "https://loginbp.ggwhitehawk.com/MajorLogin"
        self.HeadErs = {
            'X-Unity-Version': '2022.3.47f1',
            'ReleaseVersion': 'OB54',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-GA': 'v1 1',
            'Content-Length': '928',
            'User-Agent': 'UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
            'Host': 'loginbp.ggwhitehawk.com',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'deflate, gzip'
        }
        self.dT = bytes.fromhex('1a13323032352d31312d32362030313a35313a3238220966726565206669726528013a07312e3132362e314232416e64726f6964204f532039202f204150492d3238202850492f72656c2e636a772e32303232303531382e313134313333294a0848616e6468656c64520c4d544e2f537061636574656c5a045749464960800a68d00572033234307a2d7838362d3634205353453320535345342e3120535345342e32204156582041565832207c2032343030207c20348001e61e8a010f416472656e6f2028544d292036343092010d4f70656e474c20455320332e329a012b476f6f676c657c36323566373136662d393161372d343935622d396631362d303866653964336336353333a2010e3137362e32382e3133392e313835aa01026172b201203433303632343537393364653836646134323561353263616164663231656564ba010134c2010848616e6468656c64ca010d4f6e65506c7573204135303130ea014063363961653230386661643732373338623637346232383437623530613361316466613235643161313966616537343566633736616334613065343134633934f00101ca020c4d544e2f537061636574656cd2020457494649ca03203161633462383065636630343738613434323033626638666163363132306635e003b5ee02e8039a8002f003af13f80384078004a78f028804b5ee029004a78f029804b5ee02b00404c80401d2043d2f646174612f6170702f636f6d2e6474732e667265656669726574682d66705843537068495636644b43376a4c2d574f7952413d3d2f6c69622f61726de00401ea045f65363261623935333464386662356662303831646233333861636233333439317c2f646174612f6170702f636f6d2e6474732e667265656669726574682d66705843537068495636644b43376a4c2d574f7952413d3d2f626173652e61706bf00406f804018a050233329a050a32303139313139303236a80503b205094f70656e474c455332b805ff01c00504e005be7eea05093372645f7061727479f205704b717348543857393347646347335a6f7a454e6646775648746d377171316552554e6149444e67526f626f7a4942744c4f695943633459367a767670634943787a514632734f453463627974774c7334785a62526e70524d706d5752514b6d654f35766373386e51594268777148374bf805e7e4068806019006019a060134a2060134b2062213521146500e590349510e460900115843395f005b510f685b560a6107576d0f0366')
        self.dT = self.dT.replace(b'2025-07-30 14:11:20', str(datetime.now())[:-7].encode())
        self.dT = self.dT.replace(b'c69ae208fad72738b674b2847b50a3a1dfa25d1a19fae745fc76ac4a0e414c94', Access_ToKen.encode())
        self.dT = self.dT.replace(b'4306245793de86da425a52caadf21eed', Access_Uid.encode())
        try:
            hex_data = self.dT.hex()
            encoded_data = EnC_AEs(hex_data)
            if not all(c in '0123456789abcdefABCDEF' for c in encoded_data):
                encoded_data = hex_data
            self.PaYload = bytes.fromhex(encoded_data)
        except Exception as e:
            print(f"{R}❌ Encoding error: {e}{RS}")
            self.PaYload = self.dT
        self.ResPonse = requests.post(self.UrL, headers=self.HeadErs, data=self.PaYload, verify=False)
        if self.ResPonse.status_code == 200 and len(self.ResPonse.text) > 10:
            try:
                self.BesTo_data = json.loads(DeCode_PackEt(self.ResPonse.content.hex()))
                self.JwT_ToKen = self.BesTo_data['8']['data']
                self.combined_timestamp, self.key, self.iv = self.GeT_Key_Iv(self.ResPonse.content)
                ip, port, ip2, port2 = self.GeT_LoGin_PorTs(self.JwT_ToKen, self.PaYload)
                return self.JwT_ToKen, self.key, self.iv, self.combined_timestamp, ip, port, ip2, port2
            except Exception as e:
                print(f"{R}❌ Response parsing error: {e}{RS}")
                time.sleep(5)
                return self.ToKen_GeneRaTe(Access_ToKen, Access_Uid)
        else:
            print(f"{R}❌ Token generation error, status: {self.ResPonse.status_code}{RS}")
            time.sleep(5)
            return self.ToKen_GeneRaTe(Access_ToKen, Access_Uid)

    def Get_FiNal_ToKen_0115(self):
        try:
            result = self.Guest_GeneRaTe(self.id, self.password)
            if not result:
                print(f"{Y}⚠️ Failed to get token {self.id}, retrying...{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
            token, key, iv, Timestamp, ip, port, ip2, port2 = result
            if not all([ip, port, ip2, port2]):
                print(f"{Y}⚠️ Failed to get ports {self.id}, retrying...{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
            self.JwT_ToKen = token
            try:
                self.AfTer_DeC_JwT = jwt.decode(token, options={"verify_signature": False})
                self.AccounT_Uid = self.AfTer_DeC_JwT.get('account_id')
                self.EncoDed_AccounT = hex(self.AccounT_Uid)[2:]
                self.HeX_VaLue = DecodE_HeX(Timestamp)
                self.TimE_HEx = self.HeX_VaLue
                self.JwT_ToKen_ = token.encode().hex()
                print(f'{C}🆔 Account UID: {self.AccounT_Uid}{RS}')
            except Exception as e:
                print(f"{R}❌ Token decode error {self.id}: {e}{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
            try:
                self.Header = hex(len(EnC_PacKeT(self.JwT_ToKen_, key, iv)) // 2)[2:]
                length = len(self.EncoDed_AccounT)
                self.__ = '00000000'
                if length == 9: self.__ = '0000000'
                elif length == 8: self.__ = '00000000'
                elif length == 10: self.__ = '000000'
                elif length == 7: self.__ = '000000000'
                self.Header = f'0115{self.__}{self.EncoDed_AccounT}{self.TimE_HEx}00000{self.Header}'
                self.FiNal_ToKen_0115 = self.Header + EnC_PacKeT(self.JwT_ToKen_, key, iv)
            except Exception as e:
                print(f"{R}❌ Final token error {self.id}: {e}{RS}")
                time.sleep(5)
                return self.Get_FiNal_ToKen_0115()
            self.AutH_ToKen = self.FiNal_ToKen_0115
            self.Connect_SerVer(self.JwT_ToKen, self.AutH_ToKen, ip, port, key, iv, ip2, port2)
            return self.AutH_ToKen, key, iv
        except Exception as e:
            print(f"{R}❌ {self.id} connection failed: {e}{RS}")
            time.sleep(5)
            return self.Get_FiNal_ToKen_0115()

def start_account(account):
    try:
        print(f"{G}🚀 Logging in: {account['id']}{RS}")
        FF_CLient(account['id'], account['password'])
    except Exception as e:
        time.sleep(1)
        start_account(account)

def run_accounts():
    for acc in ACCOUNTS:
        Thread(target=start_account, args=(acc,), daemon=True).start()
        time.sleep(0.2)

# ==================== স্প্যাম কন্ট্রোল ফাংশন ====================
def start_spam():
    global spam_running, spam_thread
    if spam_running:
        return False, "Spam already running"
    if not targets:
        return False, "No targets found in inv_uid.txt"
    spam_running = True
    spam_thread = Thread(target=spam_worker, daemon=True)
    spam_thread.start()
    return True, "Spam started"

def stop_spam():
    global spam_running
    spam_running = False
    return True, "Spam stopped"

def add_targets(new_uids):
    global targets
    added = []
    for uid in new_uids:
        if uid not in targets and uid.isdigit():
            targets.append(uid)
            added.append(uid)
    if added:
        save_targets(targets)
    return added

def remove_target(uid):
    global targets
    if uid in targets:
        targets.remove(uid)
        save_targets(targets)
        return True
    return False

# ==================== নিরাপত্তা (SECURITY) ====================
app.secret_key = 'admin_rahman_secret_key_123'

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

def load_registered_users():
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin@rahman.com": "rahman786"
        }
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_users, f, indent=4)
        return default_users
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_user(email, password):
    users = load_registered_users()
    users[email.lower().strip()] = password
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        print(f"Failed to save user: {e}")
        return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.headers.get('Accept') == 'application/json' or request.is_json or request.path != '/':
                return jsonify({"success": False, "message": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    
    error = None
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')
            
        users = load_registered_users()
        email_key = username.lower().strip() if username else ""
        if email_key in users and users[email_key] == password:
            session['logged_in'] = True
            if request.is_json:
                return jsonify({"success": True, "message": "Login successful"})
            return redirect(url_for('index'))
        else:
            error = "Invalid Email or Password"
            if request.is_json:
                return jsonify({"success": False, "message": error}), 401

    return render_template_string('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ADMIN RAHMAN | LOGIN</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Orbitron:wght@600;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --red-1: #ff0844;
            --red-2: #ff4e50;
            --red-3: #ff2e93;
            --glass-bg: rgba(8, 8, 12, 0.75);
            --glass-border: rgba(255, 8, 68, 0.15);
            --text-primary: #ffebf0;
            --text-secondary: rgba(255, 235, 240, 0.55);
        }
        body {
            min-height: 100vh;
            background: #040406;
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
            position: relative;
        }
        #bg-canvas, #crimson-canvas {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            z-index: 0; pointer-events: none; opacity: 0.5;
        }
        #crimson-canvas { mix-blend-mode: screen; }
        .aurora {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none;
            background: radial-gradient(ellipse at 50% 50%, rgba(255, 8, 68, 0.06) 0%, transparent 60%);
        }
        .login-card {
            position: relative;
            z-index: 2;
            background: var(--glass-bg);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 28px;
            padding: 45px 40px;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.8), 0 0 50px rgba(255, 8, 68, 0.03);
            transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
            text-align: center;
            overflow: hidden;
        }
        /* Glowing tracing beam around border */
        .login-card::after {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            border-radius: 28px;
            padding: 1.5px;
            background: linear-gradient(135deg, transparent 30%, var(--red-1) 50%, transparent 70%);
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
            background-size: 200% 200%;
            animation: borderBeam 4s linear infinite;
            opacity: 0.5;
        }
        @keyframes borderBeam {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        .login-card:hover {
            border-color: rgba(255, 8, 68, 0.4);
            box-shadow: 0 30px 70px rgba(0, 0, 0, 0.9), 0 0 60px rgba(255, 8, 68, 0.08);
            transform: translateY(-5px);
        }
        .logo-wrapper {
            margin-bottom: 25px;
            position: relative;
            display: inline-block;
        }
        .logo-glow {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            width: 140px; height: 140px;
            background: radial-gradient(circle, rgba(255, 8, 68, 0.25), transparent 70%);
            filter: blur(25px);
            z-index: -1;
        }
        .logo-icon {
            font-size: 3.2rem;
            color: var(--red-1);
            text-shadow: 0 0 35px rgba(255, 8, 68, 0.7);
            animation: boltGlow 3s ease-in-out infinite alternate;
        }
        @keyframes boltGlow {
            0% { transform: scale(0.95) rotate(-3deg); opacity: 0.85; }
            100% { transform: scale(1.05) rotate(3deg); opacity: 1; }
        }
        h2 {
            font-family: 'Orbitron', sans-serif;
            font-size: 2.1rem;
            font-weight: 900;
            letter-spacing: 2px;
            margin-bottom: 8px;
            background: linear-gradient(135deg, var(--red-1), var(--red-2), var(--red-3));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-shadow: 0 0 30px rgba(255, 8, 68, 0.15);
        }
        .subtitle {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 35px;
            letter-spacing: 6px;
            text-transform: uppercase;
            font-weight: 600;
        }
        .input-group {
            position: relative;
            margin-bottom: 22px;
            text-align: left;
        }
        .input-group i {
            position: absolute;
            left: 18px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-secondary);
            font-size: 1rem;
            transition: all 0.3s ease;
        }
        .input-group input {
            width: 100%;
            padding: 16px 16px 16px 50px;
            border-radius: 14px;
            border: 1px solid rgba(255, 8, 68, 0.15);
            background: rgba(0, 0, 0, 0.6);
            color: var(--text-primary);
            font-size: 0.95rem;
            outline: none;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
        }
        .input-group input:focus {
            border-color: var(--red-1);
            box-shadow: 0 0 25px rgba(255, 8, 68, 0.15), inset 0 0 15px rgba(255, 8, 68, 0.05);
            background: rgba(0, 0, 0, 0.75);
        }
        .input-group input:focus + i {
            color: var(--red-2);
            transform: translateY(-50%) scale(1.1);
            text-shadow: 0 0 15px rgba(255, 8, 68, 0.4);
        }
        .btn-login {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: 14px;
            font-weight: 700;
            font-size: 0.95rem;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-top: 10px;
            background: linear-gradient(135deg, var(--red-1), var(--red-3), var(--red-2));
            background-size: 200% auto;
            color: #fff;
            box-shadow: 0 5px 25px rgba(255, 8, 68, 0.3);
            border: 1px solid rgba(255, 8, 68, 0.25);
            transition: all 0.4s ease;
            font-family: 'Inter', sans-serif;
            position: relative;
            overflow: hidden;
        }
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 35px rgba(255, 8, 68, 0.5);
            background-position: right center;
        }
        .error-message {
            background: rgba(255, 71, 87, 0.08);
            border: 1px solid rgba(255, 71, 87, 0.2);
            color: #ff6b6b;
            padding: 14px 18px;
            border-radius: 14px;
            font-size: 0.88rem;
            margin-bottom: 22px;
            display: flex;
            align-items: center;
            gap: 12px;
            animation: shake 0.45s ease;
        }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-6px); }
            75% { transform: translateX(6px); }
        }
        .btn-login .ripple {
            position: absolute; border-radius: 50%; background: rgba(255,255,255,0.35);
            transform: scale(0); animation: ripple 0.6s linear; pointer-events: none;
        }
        @keyframes ripple { to { transform: scale(4); opacity: 0; } }
    </style>
</head>
<body>
    <canvas id="bg-canvas"></canvas>
    <canvas id="crimson-canvas"></canvas>
    <div class="aurora"></div>

    <div class="login-card">
        <div class="logo-wrapper">
            <div class="logo-glow"></div>
            <i class="fas fa-bolt logo-icon"></i>
        </div>
        <h2>ADMIN RAHMAN</h2>
        <div class="subtitle">ROOM SPAM SECURITY</div>

        <form method="POST">
            {% if error %}
            <div class="error-message">
                <i class="fas fa-exclamation-triangle"></i> {{ error }}
            </div>
            {% endif %}
            <div class="input-group">
                <input type="email" name="username" placeholder="Enter Gmail Address" required autocomplete="off">
                <i class="fas fa-envelope"></i>
            </div>
            <div class="input-group">
                <input type="password" name="password" placeholder="Enter Password" required>
                <i class="fas fa-lock"></i>
            </div>
            <button type="submit" class="btn-login">Unlock Terminal</button>
            <div style="margin-top: 25px; font-size: 0.85rem;">
                <span style="color: var(--text-secondary);">Don't have an account? </span>
                <a href="/register" style="color: var(--red-2); text-decoration: none; font-weight: 700; transition: color 0.2s;" onmouseover="this.style.color='var(--red-3)'" onmouseout="this.style.color='var(--red-2)'">Register Here</a>
            </div>
        </form>
    </div>

    <script>
        (function() {
            const canvas = document.getElementById('bg-canvas');
            const ctx = canvas.getContext('2d');
            let width, height;
            let particles = [];
            const numParticles = 60;
            function resize() {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();
            class Particle {
                constructor() { this.reset(); }
                reset() {
                    this.x = Math.random() * width;
                    this.y = Math.random() * height;
                    this.size = Math.random() * 2 + 0.5;
                    this.speedX = (Math.random() - 0.5) * 0.3;
                    this.speedY = (Math.random() - 0.5) * 0.3;
                    this.opacity = Math.random() * 0.5 + 0.2;
                }
                update() {
                    this.x += this.speedX; this.y += this.speedY;
                    if (this.x < 0 || this.x > width) this.speedX *= -1;
                    if (this.y < 0 || this.y > height) this.speedY *= -1;
                }
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(255, 8, 68, ${this.opacity})`;
                    ctx.fill();
                }
            }
            for (let i = 0; i < numParticles; i++) particles.push(new Particle());
            function animate() {
                ctx.clearRect(0, 0, width, height);
                particles.forEach(p => { p.update(); p.draw(); });
                requestAnimationFrame(animate);
            }
            animate();
        })();

        (function() {
            const canvas = document.getElementById('crimson-canvas');
            const ctx = canvas.getContext('2d');
            let width, height, particles = [];
            function resize() {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();
            class CrimsonParticle {
                constructor() { this.reset(); }
                reset() {
                    this.x = Math.random() * width; this.y = Math.random() * height;
                    this.size = Math.random() * 3 + 1;
                    this.speedX = (Math.random() - 0.5) * 0.4; this.speedY = (Math.random() - 0.5) * 0.4;
                    this.opacity = Math.random() * 0.5 + 0.3;
                    this.hue = Math.random() > 0.5 ? Math.random() * 10 : 350 + Math.random() * 10;
                }
                update() {
                    this.x += this.speedX; this.y += this.speedY;
                    if (this.x < 0 || this.x > width) this.speedX *= -1;
                    if (this.y < 0 || this.y > height) this.speedY *= -1;
                }
                draw() {
                    ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.shadowColor = `hsl(${this.hue}, 100%, 60%)`; ctx.shadowBlur = 15;
                    ctx.fillStyle = `hsla(${this.hue}, 100%, 70%, ${this.opacity})`; ctx.fill();
                    ctx.shadowBlur = 0;
                }
            }
            for (let i = 0; i < 40; i++) particles.push(new CrimsonParticle());
            function animate() {
                ctx.clearRect(0, 0, width, height);
                particles.forEach(p => { p.update(); p.draw(); });
                requestAnimationFrame(animate);
            }
            animate();
        })();

        document.querySelector('.btn-login').addEventListener('click', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const ripple = document.createElement('span');
            ripple.className = 'ripple';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            this.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    </script>
</body>
</html>''', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    
    error = None
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
            confirm_password = data.get('confirm_password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
        if not username or not password or not confirm_password:
            error = "Please fill in all fields"
        elif password != confirm_password:
            error = "Passwords do not match"
        elif '@' not in username or '.' not in username:
            error = "Please enter a valid Email Address"
        else:
            users = load_registered_users()
            email_key = username.lower().strip()
            if email_key in users:
                error = "Email address already registered"
            else:
                if save_user(email_key, password):
                    if request.is_json:
                        return jsonify({"success": True, "message": "Registration successful"})
                    return redirect(url_for('login'))
                else:
                    error = "Failed to register user. Try again."
                    
        if error and request.is_json:
            return jsonify({"success": False, "message": error}), 400

    return render_template_string('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ADMIN RAHMAN | REGISTER</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Orbitron:wght@600;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --red-1: #ff0844;
            --red-2: #ff4e50;
            --red-3: #ff2e93;
            --glass-bg: rgba(8, 8, 12, 0.75);
            --glass-border: rgba(255, 8, 68, 0.15);
            --text-primary: #ffebf0;
            --text-secondary: rgba(255, 235, 240, 0.55);
        }
        body {
            min-height: 100vh;
            background: #040406;
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
            position: relative;
        }
        #bg-canvas, #crimson-canvas {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            z-index: 0; pointer-events: none; opacity: 0.5;
        }
        #crimson-canvas { mix-blend-mode: screen; }
        .aurora {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none;
            background: radial-gradient(ellipse at 50% 50%, rgba(255, 8, 68, 0.06) 0%, transparent 60%);
        }
        .login-card {
            position: relative;
            z-index: 2;
            background: var(--glass-bg);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 28px;
            padding: 45px 40px;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.8), 0 0 50px rgba(255, 8, 68, 0.03);
            transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
            text-align: center;
            overflow: hidden;
        }
        /* Glowing tracing beam around border */
        .login-card::after {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            border-radius: 28px;
            padding: 1.5px;
            background: linear-gradient(135deg, transparent 30%, var(--red-1) 50%, transparent 70%);
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
            background-size: 200% 200%;
            animation: borderBeam 4s linear infinite;
            opacity: 0.5;
        }
        @keyframes borderBeam {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        .login-card:hover {
            border-color: rgba(255, 8, 68, 0.4);
            box-shadow: 0 30px 70px rgba(0, 0, 0, 0.9), 0 0 60px rgba(255, 8, 68, 0.08);
            transform: translateY(-5px);
        }
        .logo-wrapper {
            margin-bottom: 25px;
            position: relative;
            display: inline-block;
        }
        .logo-glow {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            width: 140px; height: 140px;
            background: radial-gradient(circle, rgba(255, 8, 68, 0.25), transparent 70%);
            filter: blur(25px);
            z-index: -1;
        }
        .logo-icon {
            font-size: 3.2rem;
            color: var(--red-1);
            text-shadow: 0 0 35px rgba(255, 8, 68, 0.7);
            animation: boltGlow 3s ease-in-out infinite alternate;
        }
        @keyframes boltGlow {
            0% { transform: scale(0.95) rotate(-3deg); opacity: 0.85; }
            100% { transform: scale(1.05) rotate(3deg); opacity: 1; }
        }
        h2 {
            font-family: 'Orbitron', sans-serif;
            font-size: 2.1rem;
            font-weight: 900;
            letter-spacing: 2px;
            margin-bottom: 8px;
            background: linear-gradient(135deg, var(--red-1), var(--red-2), var(--red-3));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-shadow: 0 0 30px rgba(255, 8, 68, 0.15);
        }
        .subtitle {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 35px;
            letter-spacing: 6px;
            text-transform: uppercase;
            font-weight: 600;
        }
        .input-group {
            position: relative;
            margin-bottom: 20px;
            text-align: left;
        }
        .input-group i {
            position: absolute;
            left: 18px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-secondary);
            font-size: 1rem;
            transition: all 0.3s ease;
        }
        .input-group input {
            width: 100%;
            padding: 16px 16px 16px 50px;
            border-radius: 14px;
            border: 1px solid rgba(255, 8, 68, 0.15);
            background: rgba(0, 0, 0, 0.6);
            color: var(--text-primary);
            font-size: 0.95rem;
            outline: none;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
        }
        .input-group input:focus {
            border-color: var(--red-1);
            box-shadow: 0 0 25px rgba(255, 8, 68, 0.15), inset 0 0 15px rgba(255, 8, 68, 0.05);
            background: rgba(0, 0, 0, 0.75);
        }
        .input-group input:focus + i {
            color: var(--red-2);
            transform: translateY(-50%) scale(1.1);
            text-shadow: 0 0 15px rgba(255, 8, 68, 0.4);
        }
        .btn-login {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: 14px;
            font-weight: 700;
            font-size: 0.95rem;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-top: 10px;
            background: linear-gradient(135deg, var(--red-1), var(--red-3), var(--red-2));
            background-size: 200% auto;
            color: #fff;
            box-shadow: 0 5px 25px rgba(255, 8, 68, 0.3);
            border: 1px solid rgba(255, 8, 68, 0.25);
            transition: all 0.4s ease;
            font-family: 'Inter', sans-serif;
            position: relative;
            overflow: hidden;
        }
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 35px rgba(255, 8, 68, 0.5);
            background-position: right center;
        }
        .error-message {
            background: rgba(255, 71, 87, 0.08);
            border: 1px solid rgba(255, 71, 87, 0.2);
            color: #ff6b6b;
            padding: 14px 18px;
            border-radius: 14px;
            font-size: 0.88rem;
            margin-bottom: 22px;
            display: flex;
            align-items: center;
            gap: 12px;
            animation: shake 0.45s ease;
        }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-6px); }
            75% { transform: translateX(6px); }
        }
        .btn-login .ripple {
            position: absolute; border-radius: 50%; background: rgba(255,255,255,0.35);
            transform: scale(0); animation: ripple 0.6s linear; pointer-events: none;
        }
        @keyframes ripple { to { transform: scale(4); opacity: 0; } }
    </style>
</head>
<body>
    <canvas id="bg-canvas"></canvas>
    <canvas id="crimson-canvas"></canvas>
    <div class="aurora"></div>

    <div class="login-card">
        <div class="logo-wrapper">
            <div class="logo-glow"></div>
            <i class="fas fa-bolt logo-icon"></i>
        </div>
        <h2>ADMIN RAHMAN</h2>
        <div class="subtitle">ROOM SPAM SECURITY</div>

        <form method="POST">
            {% if error %}
            <div class="error-message">
                <i class="fas fa-exclamation-triangle"></i> {{ error }}
            </div>
            {% endif %}
            <div class="input-group">
                <input type="email" name="username" placeholder="Enter Gmail Address" required autocomplete="off">
                <i class="fas fa-envelope"></i>
            </div>
            <div class="input-group">
                <input type="password" name="password" placeholder="Enter Password" required>
                <i class="fas fa-lock"></i>
            </div>
            <div class="input-group">
                <input type="password" name="confirm_password" placeholder="Confirm Password" required>
                <i class="fas fa-shield-alt"></i>
            </div>
            <button type="submit" class="btn-login">Create Account</button>
            <div style="margin-top: 25px; font-size: 0.85rem;">
                <span style="color: var(--text-secondary);">Already have an account? </span>
                <a href="/login" style="color: var(--red-2); text-decoration: none; font-weight: 700; transition: color 0.2s;" onmouseover="this.style.color='var(--red-3)'" onmouseout="this.style.color='var(--red-2)'">Login Here</a>
            </div>
        </form>
    </div>

    <script>
        (function() {
            const canvas = document.getElementById('bg-canvas');
            const ctx = canvas.getContext('2d');
            let width, height;
            let particles = [];
            const numParticles = 60;
            function resize() {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();
            class Particle {
                constructor() { this.reset(); }
                reset() {
                    this.x = Math.random() * width;
                    this.y = Math.random() * height;
                    this.size = Math.random() * 2 + 0.5;
                    this.speedX = (Math.random() - 0.5) * 0.3;
                    this.speedY = (Math.random() - 0.5) * 0.3;
                    this.opacity = Math.random() * 0.5 + 0.2;
                }
                update() {
                    this.x += this.speedX; this.y += this.speedY;
                    if (this.x < 0 || this.x > width) this.speedX *= -1;
                    if (this.y < 0 || this.y > height) this.speedY *= -1;
                }
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(255, 8, 68, ${this.opacity})`;
                    ctx.fill();
                }
            }
            for (let i = 0; i < numParticles; i++) particles.push(new Particle());
            function animate() {
                ctx.clearRect(0, 0, width, height);
                particles.forEach(p => { p.update(); p.draw(); });
                requestAnimationFrame(animate);
            }
            animate();
        })();

        (function() {
            const canvas = document.getElementById('crimson-canvas');
            const ctx = canvas.getContext('2d');
            let width, height, particles = [];
            function resize() {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();
            class CrimsonParticle {
                constructor() { this.reset(); }
                reset() {
                    this.x = Math.random() * width; this.y = Math.random() * height;
                    this.size = Math.random() * 3 + 1;
                    this.speedX = (Math.random() - 0.5) * 0.4; this.speedY = (Math.random() - 0.5) * 0.4;
                    this.opacity = Math.random() * 0.5 + 0.3;
                    this.hue = Math.random() > 0.5 ? Math.random() * 10 : 350 + Math.random() * 10;
                }
                update() {
                    this.x += this.speedX; this.y += this.speedY;
                    if (this.x < 0 || this.x > width) this.speedX *= -1;
                    if (this.y < 0 || this.y > height) this.speedY *= -1;
                }
                draw() {
                    ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.shadowColor = `hsl(${this.hue}, 100%, 60%)`; ctx.shadowBlur = 15;
                    ctx.fillStyle = `hsla(${this.hue}, 100%, 70%, ${this.opacity})`; ctx.fill();
                    ctx.shadowBlur = 0;
                }
            }
            for (let i = 0; i < 40; i++) particles.push(new CrimsonParticle());
            function animate() {
                ctx.clearRect(0, 0, width, height);
                particles.forEach(p => { p.update(); p.draw(); });
                requestAnimationFrame(animate);
            }
            animate();
        })();

        document.querySelector('.btn-login').addEventListener('click', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const ripple = document.createElement('span');
            ripple.className = 'ripple';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            this.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    </script>
</body>
</html>''', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==================== API রাউট ====================
@app.route('/status', methods=['GET'])
@login_required
def status():
    with connected_clients_lock:
        acc_count = len(connected_clients)
        acc_list = list(connected_clients.keys())
    return jsonify({
        "spam_running": spam_running,
        "targets": targets,
        "active_accounts": acc_count,
        "accounts": acc_list
    })

@app.route('/start', methods=['POST'])
@login_required
def api_start():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Missing JSON"}), 400
    uids = data.get('uids') or data.get('uid')
    if not uids:
        return jsonify({"success": False, "message": "Provide 'uid' or 'uids'"}), 400
    if isinstance(uids, str):
        uids = [uids]
    added = add_targets(uids)
    if added:
        if not spam_running:
            start_spam()
        return jsonify({"success": True, "added": added, "message": f"Added {len(added)} targets"})
    else:
        return jsonify({"success": False, "message": "No new valid UIDs"})

@app.route('/stop', methods=['POST'])
@login_required
def api_stop():
    data = request.get_json()
    if data and data.get('uid'):
        uid = data['uid']
        if remove_target(uid):
            return jsonify({"success": True, "message": f"Removed {uid}"})
        else:
            return jsonify({"success": False, "message": f"UID {uid} not found"})
    else:
        stop_spam()
        return jsonify({"success": True, "message": "Spam stopped"})

@app.route('/stop-all', methods=['POST'])
@login_required
def api_stop_all():
    stop_spam()
    return jsonify({"success": True, "message": "Spam stopped"})

@app.route('/targets', methods=['GET'])
@login_required
def api_targets():
    return jsonify({"targets": targets})

@app.route('/accounts', methods=['GET'])
@login_required
def api_accounts():
    with connected_clients_lock:
        return jsonify({"accounts": list(connected_clients.keys()), "count": len(connected_clients)})

@app.route('/reload-targets', methods=['POST'])
@login_required
def api_reload():
    load_targets("inv_uid.txt")
    return jsonify({"success": True, "targets": targets})

# ==================== WEB INTERFACE (REDESIGNED) ====================
@app.route('/')
@login_required
def index():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ADMIN RAHMAN ROOM SPAM</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Orbitron:wght@400;600;700;900&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --gold-1: #ff0844;
            --gold-2: #ff4e50;
            --gold-3: #ff2e93;
            --gold-4: #d90429;
            --gold-5: #9b2226;
            --gold-6: #ef233c;
            --glass-bg: rgba(8, 8, 12, 0.72);
            --glass-border: rgba(255, 8, 68, 0.18);
            --glass-shadow: 0 20px 50px rgba(0, 0, 0, 0.85);
            --text-primary: #ffebf0;
            --text-secondary: rgba(255, 235, 240, 0.55);
        }

        body {
            min-height: 100vh;
            background: #040406;
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            overflow-x: hidden;
            position: relative;
            margin: 0;
            padding: 0;
        }

        /* Scanline Texture Overlay */
        body::before {
            content: " ";
            display: block;
            position: fixed;
            top: 0; left: 0; bottom: 0; right: 0;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.18) 50%);
            z-index: 10;
            background-size: 100% 4px;
            pointer-events: none;
            opacity: 0.35;
        }

        /* Sweeping Scanner Line */
        .scanner-line {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 3px;
            background: linear-gradient(90deg, transparent, rgba(255, 8, 68, 0.4), transparent);
            z-index: 5;
            pointer-events: none;
            animation: scanAnimation 10s linear infinite;
        }
        @keyframes scanAnimation {
            0% { top: -5%; }
            100% { top: 105%; }
        }

        #bg-canvas {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            z-index: 0; pointer-events: none; opacity: 0.4;
        }

        #crimson-canvas {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            z-index: 1; pointer-events: none;
            mix-blend-mode: screen;
            opacity: 0.65;
        }

        .aurora-overlay {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            z-index: 1; pointer-events: none;
            background:
                radial-gradient(ellipse at 15% 15%, rgba(255, 8, 68, 0.08) 0%, transparent 60%),
                radial-gradient(ellipse at 85% 85%, rgba(219, 4, 41, 0.06) 0%, transparent 60%),
                radial-gradient(ellipse at 50% 50%, rgba(155, 34, 38, 0.04) 0%, transparent 50%);
            animation: auroraFloat 25s ease-in-out infinite alternate;
        }
        @keyframes auroraFloat {
            0% { transform: translateX(-2%) scale(1); opacity: 0.7; }
            100% { transform: translateX(2%) scale(1.05); opacity: 1; }
        }

        #loading-screen {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: #040406;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            font-family: 'Orbitron', monospace;
            color: var(--text-primary);
            transition: opacity 0.8s cubic-bezier(0.4, 0, 0.2, 1), visibility 0.8s;
        }
        #loading-screen.hidden {
            opacity: 0;
            visibility: hidden;
        }
        #loading-screen .loader-text {
            font-size: 2.2rem;
            font-weight: 900;
            letter-spacing: 8px;
            background: linear-gradient(135deg, var(--gold-1), var(--gold-3));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 25px;
            text-shadow: 0 0 45px rgba(255, 8, 68, 0.5);
            animation: textPulse 1.5s ease-in-out infinite alternate;
        }
        @keyframes textPulse {
            0% { opacity: 0.6; transform: scale(0.98); }
            100% { opacity: 1; transform: scale(1.02); }
        }
        #loading-screen .progress-bar {
            width: 320px;
            height: 4px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 0 15px rgba(255, 8, 68, 0.15);
        }
        #loading-screen .progress-bar .fill {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, var(--gold-1), var(--gold-3));
            border-radius: 10px;
            animation: loadProgress 2.2s cubic-bezier(0.1, 0.8, 0.25, 1) forwards;
            box-shadow: 0 0 15px rgba(255, 8, 68, 0.5);
        }
        @keyframes loadProgress {
            0% { width: 0%; }
            10% { width: 15%; }
            45% { width: 55%; }
            80% { width: 90%; }
            100% { width: 100%; }
        }
        .loading-sub {
            margin-top: 15px;
            font-size: 0.8rem;
            color: rgba(255, 235, 240, 0.35);
            letter-spacing: 3px;
            text-transform: uppercase;
            font-family: 'Inter', sans-serif;
            font-weight: 500;
        }

        .app-container {
            position: relative;
            z-index: 2;
            max-width: 1300px;
            margin: 0 auto;
            padding: 30px 24px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .header {
            text-align: center;
            padding: 20px 0 35px;
            position: relative;
            margin-bottom: 25px;
        }
        .header::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 20%;
            width: 60%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255, 8, 68, 0.3), transparent);
        }

        .logo-wrapper {
            position: relative;
            display: inline-block;
        }
        .logo-glow {
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 260px; height: 260px;
            background: radial-gradient(circle, rgba(255, 8, 68, 0.16), transparent 70%);
            filter: blur(45px);
            animation: logoGlowPulse 6s ease-in-out infinite alternate;
            pointer-events: none;
        }
        @keyframes logoGlowPulse {
            0% { transform: translate(-50%, -50%) scale(0.9); opacity: 0.5; }
            100% { transform: translate(-50%, -50%) scale(1.15); opacity: 0.9; }
        }

        .header h1 {
            font-size: 3.2rem;
            font-weight: 900;
            font-family: 'Orbitron', sans-serif;
            background: linear-gradient(135deg, var(--gold-1), var(--gold-3), var(--gold-2), var(--gold-6));
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: goldShift 10s ease-in-out infinite alternate;
            text-shadow: 0 0 50px rgba(255, 8, 68, 0.25);
            letter-spacing: 4px;
        }
        @keyframes goldShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        .header .sub {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            letter-spacing: 8px;
            text-transform: uppercase;
            margin-top: 5px;
            text-shadow: 0 0 20px rgba(255, 8, 68, 0.08);
        }

        /* Rotating halo */
        .halo {
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 320px; height: 320px;
            border-radius: 50%;
            border: 1px dashed rgba(255, 8, 68, 0.08);
            animation: spin 60s linear infinite;
            pointer-events: none;
        }
        @keyframes spin {
            100% { transform: translate(-50%, -50%) rotate(360deg); }
        }

        .status-bar {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 20px;
            margin-top: 25px;
            flex-wrap: wrap;
        }
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 24px;
            border-radius: 50px;
            background: rgba(8, 8, 12, 0.6);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 8, 68, 0.15);
            font-size: 0.82rem;
            letter-spacing: 0.8px;
            font-weight: 600;
            transition: all 0.3s cubic-bezier(0.165, 0.84, 0.44, 1);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.5);
            font-family: 'Orbitron', sans-serif;
        }
        .status-indicator:hover {
            border-color: rgba(255, 8, 68, 0.35);
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(255, 8, 68, 0.12);
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }
        .status-dot.running {
            background: #00ff88;
            box-shadow: 0 0 12px #00ff88;
            animation: pulse 1s infinite alternate;
        }
        .status-dot.stopped {
            background: #ff4757;
            box-shadow: 0 0 12px #ff4757;
            animation: pulse 1.2s infinite alternate;
        }
        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.7; }
            100% { transform: scale(1.2); opacity: 1; }
        }
        .status-indicator i {
            color: var(--gold-3);
        }

        .grid-main {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 24px;
            margin-top: 10px;
        }

        /* Glass Cards with Border Beam */
        .glass-card {
            background: var(--glass-bg);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 28px 26px;
            border: 1px solid var(--glass-border);
            box-shadow: var(--glass-shadow);
            transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
            position: relative;
            overflow: hidden;
        }
        .glass-card::after {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            border-radius: 24px;
            padding: 1.5px;
            background: linear-gradient(135deg, transparent 30%, var(--gold-1) 50%, transparent 70%);
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
            background-size: 200% 200%;
            animation: borderBeam 4s linear infinite;
            opacity: 0.5;
        }
        @keyframes borderBeam {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        .glass-card:hover {
            transform: translateY(-4px);
            border-color: rgba(255, 8, 68, 0.4);
            box-shadow: 0 25px 50px rgba(0,0,0,0.9), 0 0 35px rgba(255, 8, 68, 0.08);
        }
        .glass-card h3 {
            color: var(--text-primary);
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.2rem;
            font-weight: 700;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            padding-bottom: 14px;
            letter-spacing: 1px;
            font-family: 'Orbitron', sans-serif;
            text-transform: uppercase;
        }
        .glass-card h3 i {
            color: var(--gold-3);
            text-shadow: 0 0 15px rgba(255, 8, 68, 0.4);
        }

        /* Target list styling */
        .target-list {
            max-height: 220px;
            overflow-y: auto;
            margin-bottom: 12px;
            padding-right: 5px;
            scrollbar-width: thin;
            scrollbar-color: var(--gold-3) transparent;
        }
        .target-list::-webkit-scrollbar {
            width: 4px;
        }
        .target-list::-webkit-scrollbar-thumb {
            background: var(--gold-3);
            border-radius: 10px;
        }
        .target-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(0, 0, 0, 0.5);
            padding: 12px 18px;
            border-radius: 14px;
            margin-bottom: 8px;
            border-left: 3px solid rgba(255, 8, 68, 0.4);
            transition: all 0.3s;
            animation: slideIn 0.35s cubic-bezier(0.19, 1, 0.22, 1);
        }
        .target-item:hover {
            background: rgba(255, 8, 68, 0.06);
            border-left-color: var(--gold-2);
            transform: translateX(4px);
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-15px); }
            to { opacity: 1; transform: translateX(0); }
        }
        .target-item .uid {
            color: #ffebf0;
            font-weight: 600;
            font-family: 'Orbitron', monospace;
            font-size: 0.88rem;
            letter-spacing: 0.5px;
        }
        .target-item .remove-btn {
            background: none;
            border: none;
            color: rgba(255, 107, 107, 0.6);
            cursor: pointer;
            font-size: 0.95rem;
            transition: all 0.2s;
            padding: 4px 8px;
            border-radius: 8px;
        }
        .target-item .remove-btn:hover {
            color: #ff4757;
            background: rgba(255, 71, 87, 0.15);
            transform: scale(1.1);
        }

        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 35px 15px;
            color: rgba(255, 235, 240, 0.3);
            text-align: center;
        }
        .empty-state i {
            font-size: 2.2rem;
            margin-bottom: 12px;
            color: rgba(255, 8, 68, 0.35);
            text-shadow: 0 0 15px rgba(255, 8, 68, 0.1);
        }
        .empty-state p {
            font-size: 0.82rem;
            letter-spacing: 0.5px;
        }

        .input-group {
            display: flex;
            gap: 10px;
            margin-top: 12px;
            flex-wrap: wrap;
        }
        .input-group textarea {
            flex: 1;
            padding: 14px 18px;
            border: 1px solid rgba(255, 8, 68, 0.18);
            border-radius: 14px;
            background: rgba(0, 0, 0, 0.6);
            color: var(--text-primary);
            font-size: 0.92rem;
            outline: none;
            transition: all 0.3s;
            font-family: 'Inter', sans-serif;
            min-height: 70px;
            resize: vertical;
        }
        .input-group textarea:focus {
            border-color: var(--gold-2);
            box-shadow: 0 0 25px rgba(255, 8, 68, 0.18), inset 0 0 15px rgba(255, 8, 68, 0.05);
            background: rgba(0, 0, 0, 0.75);
        }

        .btn {
            padding: 14px 28px;
            border: none;
            border-radius: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            position: relative;
            overflow: hidden;
            font-family: 'Inter', sans-serif;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }
        .btn-primary {
            background: linear-gradient(135deg, var(--gold-1), var(--gold-3), var(--gold-5));
            background-size: 200% auto;
            color: #fff;
            box-shadow: 0 0 25px rgba(255, 8, 68, 0.25);
            border: 1px solid rgba(255, 8, 68, 0.2);
        }
        .btn-primary:hover {
            transform: translateY(-2px) scale(1.01);
            box-shadow: 0 8px 35px rgba(255, 8, 68, 0.45);
            background-position: right center;
        }
        .btn-danger {
            background: linear-gradient(135deg, #ff4757, #ff0844);
            color: #fff;
            box-shadow: 0 0 25px rgba(255, 8, 68, 0.25);
            border: 1px solid rgba(255, 8, 68, 0.18);
        }
        .btn-danger:hover {
            transform: translateY(-2px) scale(1.01);
            box-shadow: 0 8px 35px rgba(255, 8, 68, 0.4);
        }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
        }
        .btn-secondary:hover {
            transform: translateY(-2px) scale(1.01);
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 8, 68, 0.25);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.6);
        }
        .btn-sm {
            padding: 11px 22px;
            font-size: 0.78rem;
        }
        .btn-block {
            width: 100%;
        }

        .control-group {
            display: flex;
            gap: 14px;
            flex-wrap: wrap;
            margin-top: 12px;
        }
        .control-group .btn {
            flex: 1;
            min-width: 120px;
        }

        .stats {
            display: flex;
            justify-content: space-around;
            margin-top: 25px;
            gap: 12px;
        }
        .stats .stat {
            text-align: center;
            background: rgba(0, 0, 0, 0.45);
            border-radius: 16px;
            padding: 16px 12px;
            flex: 1;
            border: 1px solid rgba(255, 8, 68, 0.08);
            transition: all 0.3s;
        }
        .stats .stat:hover {
            border-color: rgba(255, 8, 68, 0.25);
            box-shadow: 0 0 25px rgba(255, 8, 68, 0.07);
        }
        .stats .stat .num {
            font-size: 2.1rem;
            font-weight: 900;
            font-family: 'Orbitron', monospace;
            background: linear-gradient(135deg, var(--gold-1), var(--gold-3));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            display: inline-block;
        }
        .stats .stat .label {
            font-size: 0.72rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-top: 4px;
            display: block;
            font-weight: 600;
        }

        /* Active bots list */
        .account-list {
            max-height: 180px;
            overflow-y: auto;
            font-size: 0.88rem;
            scrollbar-width: thin;
            scrollbar-color: var(--gold-3) transparent;
            padding-right: 5px;
        }
        .account-list::-webkit-scrollbar {
            width: 4px;
        }
        .account-list::-webkit-scrollbar-thumb {
            background: var(--gold-3);
            border-radius: 10px;
        }
        .account-list .acc-item {
            padding: 10px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.02);
            transition: all 0.25s;
            border-radius: 10px;
            display: flex;
            align-items: center;
            gap: 12px;
            font-family: 'Orbitron', monospace;
            font-weight: 600;
            color: #e0dbe3;
        }
        .account-list .acc-item::before {
            content: '●';
            color: #00ff88;
            font-size: 0.65rem;
            text-shadow: 0 0 10px #00ff88;
            animation: pulse 1.5s infinite alternate;
        }
        .account-list .acc-item:hover {
            background: rgba(255, 8, 68, 0.05);
            box-shadow: 0 0 20px rgba(255, 8, 68, 0.05);
            padding-left: 20px;
            color: #fff;
        }
        .account-list .acc-item:last-child {
            border-bottom: none;
        }

        /* Widget grid styling with dynamic progress bars */
        .widget-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
            margin-top: 25px;
        }
        .widget-card {
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            border-radius: 18px;
            padding: 18px 14px;
            border: 1px solid var(--glass-border);
            box-shadow: var(--glass-shadow);
            transition: all 0.3s cubic-bezier(0.165, 0.84, 0.44, 1);
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        .widget-card:hover {
            transform: translateY(-3px);
            border-color: rgba(255, 8, 68, 0.3);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.7), 0 0 30px rgba(255, 8, 68, 0.05);
        }
        .widget-card .icon {
            font-size: 1.3rem;
            color: var(--gold-2);
            margin-bottom: 6px;
            text-shadow: 0 0 15px rgba(255, 8, 68, 0.25);
        }
        .widget-card .value {
            font-size: 1.45rem;
            font-weight: 700;
            font-family: 'Orbitron', monospace;
            background: linear-gradient(135deg, var(--gold-1), var(--gold-3));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .widget-card .label {
            font-size: 0.68rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-top: 3px;
            font-weight: 600;
        }
        .widget-bar {
            width: 100%;
            height: 3px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 4px;
            margin: 8px 0 4px;
            overflow: hidden;
            position: relative;
        }
        .widget-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--gold-1), var(--gold-3));
            border-radius: 4px;
            transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 0 8px var(--gold-1);
        }

        .ai-orb {
            position: fixed;
            bottom: 40px;
            right: 40px;
            width: 85px;
            height: 85px;
            z-index: 100;
            pointer-events: auto;
            cursor: pointer;
        }
        .ai-orb .orb {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            background: radial-gradient(circle at 35% 35%, rgba(255, 8, 68, 0.35), rgba(8, 2, 3, 0.9));
            box-shadow:
                0 0 50px rgba(255, 8, 68, 0.25),
                inset 0 0 60px rgba(255, 8, 68, 0.1);
            border: 1px solid rgba(255, 8, 68, 0.25);
            animation: orbFloat 5s ease-in-out infinite alternate;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .ai-orb .orb i {
            font-size: 2.1rem;
            color: var(--text-primary);
            text-shadow: 0 0 30px rgba(255, 8, 68, 0.6);
            animation: orbIconPulse 2.5s ease-in-out infinite alternate;
        }
        @keyframes orbFloat {
            0% { transform: translateY(0px) scale(1); }
            100% { transform: translateY(-12px) scale(1.02); }
        }
        @keyframes orbIconPulse {
            0% { transform: scale(0.92); opacity: 0.75; }
            100% { transform: scale(1.08); opacity: 1; }
        }
        .ai-orb:hover .orb {
            transform: scale(1.1) translateY(-8px);
            box-shadow: 0 0 80px rgba(255, 8, 68, 0.6), inset 0 0 40px rgba(255, 8, 68, 0.2);
            border-color: rgba(255, 8, 68, 0.45);
        }

        /* CRT Terminal */
        .terminal {
            position: fixed;
            bottom: 40px;
            left: 40px;
            width: 320px;
            height: 180px;
            background: rgba(6, 6, 9, 0.85);
            backdrop-filter: blur(14px);
            border-radius: 18px;
            border: 1px solid rgba(255, 8, 68, 0.18);
            padding: 14px 16px;
            box-shadow: var(--glass-shadow);
            z-index: 100;
            overflow: hidden;
            font-family: 'Orbitron', monospace;
            font-size: 0.7rem;
            color: var(--text-secondary);
            pointer-events: none;
        }
        .terminal::before {
            content: " ";
            display: block;
            position: absolute;
            top: 0; left: 0; bottom: 0; right: 0;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%);
            z-index: 2;
            background-size: 100% 3px;
            pointer-events: none;
            opacity: 0.25;
        }
        .terminal .term-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 8, 68, 0.15);
            padding-bottom: 6px;
            margin-bottom: 8px;
            font-weight: 700;
            color: var(--gold-2);
            letter-spacing: 1px;
        }
        .terminal .term-body {
            max-height: 130px;
            overflow-y: auto;
            scrollbar-width: none;
        }
        .terminal .term-body::-webkit-scrollbar {
            display: none;
        }
        .terminal .log-line {
            opacity: 0.85;
            animation: logFade 0.3s ease forwards;
            padding: 2.5px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.01);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .terminal .log-line .time {
            color: var(--gold-2);
            margin-right: 6px;
            font-weight: 500;
        }
        @keyframes logFade {
            from { opacity: 0; transform: translateY(5px); }
            to { opacity: 0.85; transform: translateY(0); }
        }

        .toast {
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: rgba(6, 6, 9, 0.92);
            backdrop-filter: blur(16px);
            padding: 14px 30px;
            border-radius: 14px;
            border: 1px solid rgba(255, 8, 68, 0.18);
            border-left: 4px solid var(--gold-2);
            box-shadow: 0 15px 40px rgba(0, 0, 0, 0.8);
            color: var(--text-primary);
            font-size: 0.9rem;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            z-index: 999;
            max-width: 90%;
            text-align: center;
            pointer-events: none;
            opacity: 0;
            font-weight: 500;
        }
        .toast.show {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }
        .toast.error {
            border-left-color: #ff4757;
            border-color: rgba(255, 71, 87, 0.25);
        }

        @media (max-width: 992px) {
            .header h1 { font-size: 2.6rem; }
            .grid-main { grid-template-columns: 1fr; }
            .widget-grid { grid-template-columns: repeat(4, 1fr); }
            .terminal { display: none; }
        }
        @media (max-width: 600px) {
            .header h1 { font-size: 1.8rem; }
            .status-indicator { padding: 6px 16px; font-size: 0.75rem; }
            .widget-grid { grid-template-columns: repeat(2, 1fr); }
            .stats .stat .num { font-size: 1.8rem; }
            .ai-orb { right: 15px; bottom: 15px; width: 65px; height: 65px; }
        }
    </style>
</head>
<body>
    <div class="scanner-line"></div>

    <!-- ============================================================
    LOADING SCREEN
    ============================================================ -->
    <div id="loading-screen">
        <div class="loader-text">INITIALIZING</div>
        <div class="progress-bar"><div class="fill"></div></div>
        <div class="loading-sub">Loading ROOM SPAM SYSTEM...</div>
    </div>

    <canvas id="bg-canvas"></canvas>
    <canvas id="crimson-canvas"></canvas>
    <div class="aurora-overlay"></div>

    <div class="app-container">
        <a href="/logout" class="btn btn-secondary btn-sm" style="position: absolute; top: 20px; right: 20px; z-index: 10;"><i class="fas fa-sign-out-alt"></i> Logout</a>

        <header class="header">
            <div class="logo-wrapper">
                <div class="logo-glow"></div>
                <div class="halo"></div>
                <h1><i class="fas fa-bolt" style="background: none; -webkit-text-fill-color: initial; color: var(--gold-3); text-shadow: 0 0 40px rgba(255,8,68,0.6); margin-right: 12px;"></i> ADMIN RAHMAN</h1>
            </div>
            <div class="sub"> Room Invite Dashboard</div>
            <div class="status-bar">
                <span class="status-indicator">
                    <span class="status-dot stopped" id="statusDot"></span>
                    <span id="statusText">Stopped</span>
                </span>
                <span class="status-indicator">
                    <i class="fas fa-users"></i> <span id="accCount">0</span> bots
                </span>
                <span class="status-indicator">
                    <i class="fas fa-bullseye"></i> <span id="targetCount">0</span> targets
                </span>
            </div>
        </header>

        <div class="grid-main">
            <!-- Targets Card -->
            <div class="glass-card">
                <h3><i class="fas fa-crosshairs"></i> Targets</h3>
                <div class="target-list" id="targetList"></div>
                <div class="input-group">
                    <textarea id="addTargetsInput" placeholder="Enter UID(s) comma separated"></textarea>
                </div>
                <div class="input-group" style="margin-top:5px;">
                    <button class="btn btn-primary btn-sm" id="addTargetsBtn"><i class="fas fa-plus"></i> Add & Start</button>
                    <button class="btn btn-secondary btn-sm" id="reloadTargetsBtn"><i class="fas fa-sync-alt"></i> Reload</button>
                </div>
            </div>

            <!-- Controls Card -->
            <div class="glass-card">
                <h3><i class="fas fa-play-circle"></i> Control</h3>
                <div class="control-group">
                    <button class="btn btn-primary btn-block" id="startBtn"><i class="fas fa-play"></i> Start Spam</button>
                    <button class="btn btn-danger btn-block" id="stopBtn"><i class="fas fa-stop"></i> Stop Spam</button>
                </div>
                <div style="margin-top:15px;">
                    <button class="btn btn-secondary btn-sm" id="stopAllBtn"><i class="fas fa-ban"></i> Stop All</button>
                </div>
                <div class="stats">
                    <div class="stat">
                        <div class="num" id="statTargets">0</div>
                        <span class="label">Targets</span>
                    </div>
                    <div class="stat">
                        <div class="num" id="statAccounts">0</div>
                        <span class="label">Bots</span>
                    </div>
                </div>
            </div>

            <!-- Accounts Card -->
            <div class="glass-card">
                <h3><i class="fas fa-robot"></i> Active Bots</h3>
                <div class="account-list" id="accountList"></div>
                <div style="margin-top:10px; text-align:right; font-size:0.8rem; color:var(--text-secondary);">
                    <span id="accCountSmall">0</span> connected
                </div>
            </div>
        </div>

        <div class="widget-grid">
            <div class="widget-card">
                <div class="icon"><i class="fas fa-microchip"></i></div>
                <div class="value" id="cpuWidget">0%</div>
                <div class="widget-bar"><div class="widget-bar-fill" id="cpuBar" style="width: 0%"></div></div>
                <div class="label">CPU</div>
            </div>
            <div class="widget-card">
                <div class="icon"><i class="fas fa-memory"></i></div>
                <div class="value" id="ramWidget">0%</div>
                <div class="widget-bar"><div class="widget-bar-fill" id="ramBar" style="width: 0%"></div></div>
                <div class="label">RAM</div>
            </div>
            <div class="widget-card">
                <div class="icon"><i class="fas fa-tachometer-alt"></i></div>
                <div class="value" id="fpsWidget">60</div>
                <div class="widget-bar"><div class="widget-bar-fill" id="fpsBar" style="width: 100%"></div></div>
                <div class="label">FPS</div>
            </div>
            <div class="widget-card">
                <div class="icon"><i class="fas fa-wifi"></i></div>
                <div class="value" id="networkWidget">0 ms</div>
                <div class="widget-bar"><div class="widget-bar-fill" id="latencyBar" style="width: 30%"></div></div>
                <div class="label">Latency</div>
            </div>
            <div class="widget-card">
                <div class="icon"><i class="fas fa-clock"></i></div>
                <div class="value" id="clockWidget">00:00</div>
                <div class="widget-bar"><div class="widget-bar-fill" style="width: 100%"></div></div>
                <div class="label">Time</div>
            </div>
            <div class="widget-card">
                <div class="icon"><i class="fas fa-calendar-alt"></i></div>
                <div class="value" id="dateWidget">--</div>
                <div class="widget-bar"><div class="widget-bar-fill" style="width: 100%"></div></div>
                <div class="label">Date</div>
            </div>
            <div class="widget-card">
                <div class="icon"><i class="fas fa-chart-line"></i></div>
                <div class="value" id="requestsWidget">0</div>
                <div class="widget-bar"><div class="widget-bar-fill" id="requestsBar" style="width: 0%"></div></div>
                <div class="label">Requests</div>
            </div>
            <div class="widget-card">
                <div class="icon"><i class="fas fa-rocket"></i></div>
                <div class="value" id="reqPerSecWidget">0</div>
                <div class="widget-bar"><div class="widget-bar-fill" id="reqPerSecBar" style="width: 0%"></div></div>
                <div class="label">Req/s</div>
            </div>
        </div>

        <footer class="footer" style="text-align:center; margin-top:40px; padding-top:20px; border-top:1px solid rgba(255,255,255,0.05); color:var(--text-secondary); font-size:0.9rem; letter-spacing:1px;">
            <i class="fas fa-heart" style="color:#ff6b6b; text-shadow:0 0 15px rgba(255,107,107,0.3);"></i>
            <span id="footerText"></span>
        </footer>
    </div>

    <div class="ai-orb" id="aiOrb">
        <div class="orb">
            <i class="fas fa-robot"></i>
        </div>
    </div>

    <div class="terminal" id="terminal">
        <div class="term-header">
            <span><i class="fas fa-terminal"></i> SYSTEM</span>
            <span><i class="fas fa-circle" style="color:#00ff88; font-size:0.5rem; text-shadow:0 0 10px #00ff88; animation: pulse 1s infinite alternate;"></i> ONLINE</span>
        </div>
        <div class="term-body" id="termBody"></div>
    </div>

    <div class="toast" id="toast"></div>

    <script>
        (function() {
            const canvas = document.getElementById('crimson-canvas');
            const ctx = canvas.getContext('2d');
            let width, height, particles = [];
            const num = 80;

            function resize() {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();

            class CrimsonParticle {
                constructor() { this.reset(); }
                reset() {
                    this.x = Math.random() * width;
                    this.y = Math.random() * height;
                    this.size = Math.random() * 3 + 1;
                    this.speedX = (Math.random() - 0.5) * 0.4;
                    this.speedY = (Math.random() - 0.5) * 0.4;
                    this.opacity = Math.random() * 0.5 + 0.3;
                    this.hue = Math.random() > 0.5 ? Math.random() * 10 : 350 + Math.random() * 10;
                }
                update() {
                    this.x += this.speedX;
                    this.y += this.speedY;
                    if (this.x < 0 || this.x > width) this.speedX *= -1;
                    if (this.y < 0 || this.y > height) this.speedY *= -1;
                }
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.shadowColor = `hsl(${this.hue}, 100%, 60%)`;
                    ctx.shadowBlur = 20;
                    ctx.fillStyle = `hsla(${this.hue}, 100%, 70%, ${this.opacity})`;
                    ctx.fill();
                    ctx.shadowBlur = 0;
                }
            }

            for (let i = 0; i < num; i++) particles.push(new CrimsonParticle());

            function animate() {
                ctx.clearRect(0, 0, width, height);
                particles.forEach(p => {
                    p.update();
                    p.draw();
                });
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x;
                        const dy = particles[i].y - particles[j].y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < 150) {
                            ctx.beginPath();
                            ctx.moveTo(particles[i].x, particles[i].y);
                            ctx.lineTo(particles[j].x, particles[j].y);
                            ctx.strokeStyle = `rgba(255, 8, 68, ${0.12 * (1 - dist/150)})`;
                            ctx.lineWidth = 0.6;
                            ctx.stroke();
                        }
                    }
                }
                requestAnimationFrame(animate);
            }
            animate();
        })();

        // CRT Terminal Logic
        const systemConsole = (function() {
            const termBody = document.getElementById('termBody');
            const logTypes = {
                SYSTEM: 'var(--gold-1)',
                INFO: 'var(--text-secondary)',
                SUCCESS: '#00ff88',
                WARNING: '#ffaa00',
                AICORE: '#c77dff'
            };
            const defaultLogs = [
                ['Monitoring network interface...', 'INFO'],
                ['AI Diagnostics: CPU core temperature nominal', 'AICORE'],
                ['Target coordinates synchronized', 'SUCCESS'],
                ['Refreshing session tokens...', 'INFO'],
                ['Memory pool garbage collector triggered', 'INFO'],
                ['All active bot sockets stable', 'SUCCESS'],
                ['Spammer thread latency verified (22ms)', 'INFO'],
                ['System threat level: Minimum', 'AICORE'],
                ['Database connection established', 'SUCCESS'],
                ['System monitoring active', 'INFO']
            ];
            let logIndex = 0;

            function addLog(text, type='INFO') {
                const line = document.createElement('div');
                line.className = 'log-line';
                const time = new Date().toLocaleTimeString();
                const color = logTypes[type] || 'var(--text-secondary)';
                line.innerHTML = `<span class="time">[${time}]</span> <span style="color: ${color}">[${type}]</span> ${text}`;
                termBody.appendChild(line);
                if (termBody.children.length > 25) {
                    termBody.removeChild(termBody.firstChild);
                }
                termBody.scrollTop = termBody.scrollHeight;
            }

            // Expose globally so AI Orb can call it
            window.addSystemLog = addLog;

            setTimeout(() => {
                addLog('Initializing JXE System...', 'SYSTEM');
                setTimeout(() => addLog('AI Core loaded successfully', 'AICORE'), 500);
                setTimeout(() => addLog('Web Dashboard initialized', 'SUCCESS'), 1000);
                setInterval(() => {
                    const log = defaultLogs[logIndex % defaultLogs.length];
                    addLog(log[0], log[1]);
                    logIndex++;
                }, 3500);
            }, 1500);

            return { addLog };
        })();

        // AI Orb Diagnostics click
        document.getElementById('aiOrb').addEventListener('click', () => {
            const aiLogs = [
                ['Initiating deep diagnostics sweep...', 'AICORE'],
                ['Querying connection pool nodes...', 'AICORE'],
                ['All active bot payloads authenticated.', 'SUCCESS'],
                ['Local encryption keys validated.', 'SUCCESS'],
                ['Overall status: Fully Secure.', 'SUCCESS']
            ];
            aiLogs.forEach((log, idx) => {
                setTimeout(() => {
                    window.addSystemLog(log[0], log[1]);
                }, idx * 450);
            });
            const orb = document.querySelector('.ai-orb .orb');
            orb.style.transform = 'scale(1.2)';
            orb.style.borderColor = 'var(--gold-3)';
            orb.style.boxShadow = '0 0 100px rgba(255, 8, 68, 0.85)';
            setTimeout(() => {
                orb.style.transform = '';
                orb.style.borderColor = '';
                orb.style.boxShadow = '';
            }, 1000);
        });

        // Widget updating loop
        (function() {
            function updateWidgets() {
                const cpuVal = Math.floor(Math.random() * 45 + 15);
                document.getElementById('cpuWidget').textContent = cpuVal + '%';
                document.getElementById('cpuBar').style.width = cpuVal + '%';
                
                const ramVal = Math.floor(Math.random() * 30 + 25);
                document.getElementById('ramWidget').textContent = ramVal + '%';
                document.getElementById('ramBar').style.width = ramVal + '%';
                
                const fpsVal = Math.floor(Math.random() * 4 + 58);
                document.getElementById('fpsWidget').textContent = fpsVal;
                document.getElementById('fpsBar').style.width = (fpsVal / 60 * 100) + '%';
                
                const latVal = Math.floor(Math.random() * 25 + 12);
                document.getElementById('networkWidget').textContent = latVal + ' ms';
                document.getElementById('latencyBar').style.width = (latVal / 100 * 100) + '%';
                
                const now = new Date();
                document.getElementById('clockWidget').textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                document.getElementById('dateWidget').textContent = now.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
                
                const bots = parseInt(document.getElementById('accCount')?.textContent || '0');
                const targets = parseInt(document.getElementById('targetCount')?.textContent || '0');
                const req = bots * targets * 4;
                document.getElementById('requestsWidget').textContent = req;
                document.getElementById('requestsBar').style.width = Math.min(100, (req / 100 * 100)) + '%';
                
                const rps = Math.floor(req / 5);
                document.getElementById('reqPerSecWidget').textContent = rps;
                document.getElementById('reqPerSecBar').style.width = Math.min(100, (rps / 20 * 100)) + '%';
            }
            updateWidgets();
            setInterval(updateWidgets, 2500);
        })();

        // Loading Screen Auto-Hide
        setTimeout(() => {
            document.getElementById('loading-screen').classList.add('hidden');
        }, 3000);

        document.getElementById('footerText').textContent = "Made By ADMIN RAHMAN";

        // Mouse Spotlight Glow Effect
        (function() {
            const spotlight = document.createElement('div');
            spotlight.style.cssText = `
                position: fixed;
                top: 0; left: 0;
                width: 100%; height: 100%;
                pointer-events: none;
                z-index: 0;
                background: radial-gradient(circle at var(--mx, 50%) var(--my, 50%), rgba(255, 8, 68, 0.035) 0%, transparent 65%);
                transition: background 0.05s;
            `;
            document.body.appendChild(spotlight);
            document.addEventListener('mousemove', (e) => {
                const x = e.clientX / window.innerWidth * 100;
                const y = e.clientY / window.innerHeight * 100;
                spotlight.style.setProperty('--mx', x + '%');
                spotlight.style.setProperty('--my', y + '%');
            });
        })();

        // Buttons Ripple Effect
        document.querySelectorAll('.btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                const rect = this.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                const ripple = document.createElement('span');
                ripple.className = 'ripple';
                ripple.style.left = x + 'px';
                ripple.style.top = y + 'px';
                ripple.style.width = ripple.style.height = '20px';
                this.appendChild(ripple);
                setTimeout(() => ripple.remove(), 600);
            });
        });
    </script>

    <script>
        // Canvas Particles (Original Background)
        (function() {
            const canvas = document.getElementById('bg-canvas');
            const ctx = canvas.getContext('2d');
            let width, height, particles = [];
            const numParticles = 100;
            let mouseX = -9999, mouseY = -9999;

            function resize() {
                width = canvas.width = window.innerWidth;
                height = canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();

            class Particle {
                constructor() { this.reset(); }
                reset() {
                    this.x = Math.random() * width;
                    this.y = Math.random() * height;
                    this.size = Math.random() * 2 + 0.5;
                    this.speedX = (Math.random() - 0.5) * 0.35;
                    this.speedY = (Math.random() - 0.5) * 0.35;
                    this.opacity = Math.random() * 0.5 + 0.25;
                }
                update() {
                    this.x += this.speedX;
                    this.y += this.speedY;
                    const dx = mouseX - this.x;
                    const dy = mouseY - this.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 180) {
                        const force = (180 - dist) / 180 * 0.025;
                        this.x += dx * force;
                        this.y += dy * force;
                    }
                    if (this.x < 0 || this.x > width) this.speedX *= -1;
                    if (this.y < 0 || this.y > height) this.speedY *= -1;
                }
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(255, 8, 68, ${this.opacity})`;
                    ctx.fill();
                }
            }

            for (let i = 0; i < numParticles; i++) particles.push(new Particle());

            function animate() {
                ctx.clearRect(0, 0, width, height);
                particles.forEach(p => {
                    p.update();
                    p.draw();
                });
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x;
                        const dy = particles[i].y - particles[j].y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < 100) {
                            ctx.beginPath();
                            ctx.moveTo(particles[i].x, particles[i].y);
                            ctx.lineTo(particles[j].x, particles[j].y);
                            ctx.strokeStyle = `rgba(255, 8, 68, ${0.08 * (1 - dist/100)})`;
                            ctx.lineWidth = 0.5;
                            ctx.stroke();
                        }
                    }
                }
                requestAnimationFrame(animate);
            }
            animate();

            document.addEventListener('mousemove', (e) => {
                mouseX = e.clientX;
                mouseY = e.clientY;
            });
            document.addEventListener('mouseleave', () => {
                mouseX = -9999;
                mouseY = -9999;
            });
        })();

        // API interaction logic
        async function apiFetch(endpoint, options = {}) {
            const res = await fetch(endpoint, {
                ...options,
                headers: { 'Content-Type': 'application/json', ...options.headers }
            });
            return res.json();
        }

        function showToast(msg, isError = false) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast show' + (isError ? ' error' : '');
            clearTimeout(t._timer);
            t._timer = setTimeout(() => t.classList.remove('show'), 3500);
        }

        async function updateUI() {
            try {
                const status = await apiFetch('/status');
                const accounts = await apiFetch('/accounts');

                const dot = document.getElementById('statusDot');
                const statusText = document.getElementById('statusText');
                if (status.spam_running) {
                    dot.className = 'status-dot running';
                    statusText.textContent = 'Running';
                } else {
                    dot.className = 'status-dot stopped';
                    statusText.textContent = 'Stopped';
                }

                document.getElementById('accCount').textContent = status.active_accounts || 0;
                document.getElementById('targetCount').textContent = status.targets ? status.targets.length : 0;
                document.getElementById('statTargets').textContent = status.targets ? status.targets.length : 0;
                document.getElementById('statAccounts').textContent = status.active_accounts || 0;
                document.getElementById('accCountSmall').textContent = status.active_accounts || 0;

                const targetList = document.getElementById('targetList');
                targetList.innerHTML = '';
                if (status.targets && status.targets.length) {
                    status.targets.forEach(uid => {
                        const div = document.createElement('div');
                        div.className = 'target-item';
                        div.innerHTML = `
                            <span class="uid">${uid}</span>
                            <button class="remove-btn" data-uid="${uid}"><i class="fas fa-times"></i></button>
                        `;
                        div.querySelector('.remove-btn').addEventListener('click', (e) => {
                            const uid = e.currentTarget.dataset.uid;
                            removeTarget(uid);
                        });
                        targetList.appendChild(div);
                    });
                } else {
                    targetList.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-crosshairs fa-spin" style="animation-duration: 6s; opacity: 0.6;"></i>
                            <p>No active target coordinates set</p>
                        </div>
                    `;
                }

                const accList = document.getElementById('accountList');
                accList.innerHTML = '';
                if (accounts.accounts && accounts.accounts.length) {
                    accounts.accounts.forEach(acc => {
                        const div = document.createElement('div');
                        div.className = 'acc-item';
                        div.textContent = acc;
                        accList.appendChild(div);
                    });
                } else {
                    accList.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-satellite-dish" style="animation: pulse 1.5s infinite alternate; opacity: 0.6;"></i>
                            <p>Waiting for bot connections...</p>
                        </div>
                    `;
                }

            } catch (e) {
                console.error('Update error', e);
            }
        }

        async function addTargets() {
            const input = document.getElementById('addTargetsInput');
            const raw = input.value.trim();
            if (!raw) { showToast('Please enter at least one UID', true); return; }
            const uids = raw.split(',').map(s => s.trim()).filter(s => s.length > 0 && /^\\d+$/.test(s));
            if (!uids.length) { showToast('No valid UIDs found', true); return; }
            try {
                const result = await apiFetch('/start', { method: 'POST', body: JSON.stringify({ uids }) });
                if (result.success) {
                    showToast(result.message || 'Added targets and started spam!');
                    input.value = '';
                    updateUI();
                } else {
                    showToast(result.message || 'Failed to add targets', true);
                }
            } catch (e) {
                showToast('Error contacting server', true);
            }
        }

        async function removeTarget(uid) {
            try {
                const result = await apiFetch('/stop', { method: 'POST', body: JSON.stringify({ uid }) });
                if (result.success) {
                    showToast(`Removed ${uid}`);
                    updateUI();
                } else {
                    showToast(result.message || 'Failed to remove', true);
                }
            } catch (e) {
                showToast('Error', true);
            }
        }

        async function startSpam() {
            try {
                const status = await apiFetch('/status');
                if (!status.targets || status.targets.length === 0) {
                    showToast('No targets available. Add some first.', true);
                    return;
                }
                const result = await apiFetch('/start', { method: 'POST', body: JSON.stringify({ uids: status.targets }) });
                if (result.success) {
                    showToast('Spam started!');
                    updateUI();
                } else {
                    showToast(result.message || 'Failed to start', true);
                }
            } catch (e) {
                showToast('Error', true);
            }
        }

        async function stopSpam() {
            try {
                const result = await apiFetch('/stop-all', { method: 'POST' });
                if (result.success) {
                    showToast('Spam stopped');
                    updateUI();
                } else {
                    showToast(result.message || 'Failed to stop', true);
                }
            } catch (e) {
                showToast('Error', true);
            }
        }

        async function reloadTargets() {
            try {
                const result = await apiFetch('/reload-targets', { method: 'POST' });
                if (result.success) {
                    showToast('Targets reloaded from file');
                    updateUI();
                } else {
                    showToast('Reload failed', true);
                }
            } catch (e) {
                showToast('Error', true);
            }
        }

        document.getElementById('addTargetsBtn').addEventListener('click', addTargets);
        document.getElementById('startBtn').addEventListener('click', startSpam);
        document.getElementById('stopBtn').addEventListener('click', stopSpam);
        document.getElementById('stopAllBtn').addEventListener('click', stopSpam);
        document.getElementById('reloadTargetsBtn').addEventListener('click', reloadTargets);

        updateUI();
        setInterval(updateUI, 3000);
    </script>
</body>
</html>'''

# ==================== MAIN ====================
def main():
    print(f"""
{C}{BOLD}
╔═══════════════════════════════════════════════╗
║  🎖️ ADMIN RAHMAN ROOM SPAM STARTED 🎖️        ║
║             ONLY ROOM SPAM                    ║
║         👑 Developer: ADMIN RAHMAN            ║
║   Web UI available at http://0.0.0.0:5000     ║
╚═══════════════════════════════════════════════╝
{RS}
""")
    load_targets("inv_uid.txt")
    Thread(target=run_accounts, daemon=True).start()
    time.sleep(3)  # কিছু অ্যাকাউন্ট সংযুক্ত হোক
    if targets:
        start_spam()  # স্বয়ংক্রিয় শুরু

    # Flask চালান
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

if __name__ == "__main__":
    try:
        import aiohttp
        import jwt
    except ImportError:
        os.system("pip install aiohttp pyjwt")
    main()
