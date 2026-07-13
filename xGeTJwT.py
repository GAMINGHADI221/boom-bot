import requests , time , binascii , json , urllib3 , random
from datetime import datetime
from Black import *
from multiprocessing.dummy import Pool as ThreadPool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def Ua():
    TmP = "GarenaMSDK/4.0.13 ({}; {}; {};)"
    return TmP.format(random.choice(["iPhone 13 Pro", "iPhone 14", "iPhone XR", "Galaxy S22", "Note 20", "OnePlus 9", "Mi 11"]) , 
                     random.choice(["iOS 17", "iOS 18", "Android 13", "Android 14"]) , 
                     random.choice(["en-SG", "en-US", "fr-FR", "id-ID", "th-TH", "vi-VN"]))

def xGeT(u, p):
    """الدالة المعدلة لاستخدام UID و PW مباشرة من السكريبت الرئيسي"""
    print(f"جاري توليد التوكن لـ UID: {u}")
    try:
        r = requests.Session().post(
            "https://100067.connect.garena.com/oauth/guest/token/grant",
            headers={
                "Host": "100067.connect.garena.com",
                "User-Agent": Ua(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "close"
            },
            data={
                "uid": u,
                "password": p,
                "response_type": "token",
                "client_type": "2",
                "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
                "client_id": "100067"
            },
            verify=False
        )
        
        if r.status_code == 200:
            T = r.json()
            print("تم الحصول على التوكن بنجاح من Garena")
            a, o = T["access_token"], T["open_id"]
            jwt_token = xJwT(a, o)
            if jwt_token:
                print("تم توليد JWT بنجاح")
                return jwt_token
            else:
                print("فشل في توليد JWT")
                return None
        else:
            print(f"خطأ في الاستجابة من Garena: {r.status_code}")
            return None
    except Exception as e:
        print(f"حدث خطأ في xGeT: {str(e)}")
        return None

def xJwT(a, o):
    """دالة توليد JWT باستخدام التوكن المباشر"""
    try:
        dT = bytes.fromhex('1a13323032362d30312d31342030393a34383a3038220966726565206669726528013a07322e3132312e31423a416e64726f6964204f532039202f204150492d32382028505133422e3139303830312e31303130313834362f47393635305a48553241524336294a0848616e6468656c645207566572697a6f6e5a045749464960800f68b80872033238307a2141524d3634204650204153494d442041455320564d48207c2032383635207c20348001bb178a010f416472656e6f2028544d29203634309201134f70656e474c20455320332e312076312e34369a012b476f6f676c657c33346137646364662d613764352d346362362d386437652d336230653434386130633537a2010d3232332e3139312e35312e3839aa0102656eba010134c2010848616e6468656c64ca010430374051f00101ca0207566572697a6f6ed2020457494649ca03203734323862323533646566633136343031386336303461316562626665626466e0038b9b02e803e7f401f003d713f803bf058004b2c301880484d0019004e0810298048b9b02c80403d2043f2f646174612f6170702f636f6d2e6474732e667265656669726574682d59504b4d386a484577414a6c68706d68446876354d513d3d2f6c69622f61726d3634e00401ea045f35623839326161616264363838653537316636383830353331313861313632627c2f646174612f6170702f636f6d2e6474732e667265656669726574682d59504b4d386a484577414a6c68706d68446876354d513d3d2f626173652e61706bf00403f804028a050236349a050a32303139313138363935b205094f70656e474c455332b805ff7fc00504ca0530467751565467555058315561556c6c4444776357435242705741554f556773764131736e576c42614f316b4659673d3de005fc69ea0507616e64726f6964f2055c4b71734854796d77352f354742323359476e6955594e322f71343747415472713765466552617466304e6b774c4b454d5130504b35424b456b37326450666c4178556c454269723656746579383358714635393371736c386877593df805b9db068806019006019a060134a2060134')
        
        # تحديث البيانات الديناميكية
        dT = dT.replace(b'2025-07-30 14:11:20', str(datetime.now())[:-7].encode())
        dT = dT.replace('4e79affe31414901544eaabebc4705738fe683a92dd4c5ee3db33662b2e9664f', a.encode())
        dT = dT.replace(b'4306245793de86da425a52caadf21eed', o.encode())
        
        PyL = bytes.fromhex(EnC_AEs(dT.hex()))
        r = requests.Session().post(
            "https://loginbp.ggwhitehawk.com/MajorLogin",
            headers={
                "Expect": "100-continue",
                "X-Unity-Version": "2018.4.11f1",
                "X-GA": "v1 1",
                "ReleaseVersion": "OB51",
                "Authorization": "Bearer ",
                "Host": "loginbp.ggwhitehawk.com"
            },
            data=PyL,
            verify=False
        )
        
        if r.status_code == 200:
            response_data = json.loads(DeCode_PackEt(binascii.hexlify(r.content).decode('utf-8')))
            return response_data['8']['data']
        else:
            print(f"خطأ في MajorLogin: {r.status_code}")
            return None
    except Exception as e:
        print(f"حدث خطأ في xJwT: {str(e)}")
        return None