# PyIAPToolKit

> 基于 PyQt6 + Fluent Design 的 STM32 IAP 上位机工具套件，涵盖 AES-256 加密 + Ed25519 签名固件打包流水线、HKDF 设备绑定密钥派生、YMODEM 串口传输、PyOCD SWD 烧录、双差分引擎、LVGL 资源提取等核心技术。

📘 **详细设计与实现文档**：[PyIAPToolKit：STM32 IAP 上位机工具套件设计与实现](https://lingjia007.github.io/Hugo_Web/p/pyiaptoolkitstm32-iap-%E4%B8%8A%E4%BD%8D%E6%9C%BA%E5%B7%A5%E5%85%B7%E5%A5%97%E4%BB%B6%E8%AE%BE%E8%AE%A1%E4%B8%8E%E5%AE%9E%E7%8E%B0/)

📦 **发行版下载**：[v1.0.0](https://github.com/Lingjia007/PyIAPToolKit/releases/tag/v1.0.0)

---

## 目录

- [一、功能矩阵](#一功能矩阵)
- [二、技术栈](#二技术栈)
- [三、项目结构](#三项目结构)
- [四、应用架构](#四应用架构)
- [五、固件打包流水线（核心）](#五固件打包流水线核心)
- [六、HKDF 设备绑定密钥派生](#六hkdf-设备绑定密钥派生)
- [七、AES-256 加密模块](#七aes-256-加密模块)
- [八、Ed25519 数字签名](#八ed25519-数字签名)
- [九、串口终端与 YMODEM 传输](#九串口终端与-ymodem-传输)
- [十、PyOCD SWD 烧录](#十pyocd-swd-烧录)
- [十一、双差分引擎](#十一双差分引擎)
- [十二、支付宝沙箱与自定义串口协议](#十二支付宝沙箱与自定义串口协议)
- [十三、HTML UI 提取（LVGL 资源）](#十三html-ui-提取lvgl-资源)
- [十四、安全链路全景](#十四安全链路全景)
- [十五、快速开始](#十五快速开始)

---

## 一、功能矩阵

| 功能 | 描述 |
|---|---|
| 串口终端 | 多标签 VT100 终端，支持 YMODEM 固件传输 |
| AES 加解密 | 5 种模式（CBC/ECB/CTR/CFB/OFB），HKDF 密钥派生 |
| 固件头封装 | 64 字节二进制头，含版本/算法/安全计数器/HMAC 校验 |
| Ed25519 签名 | 密钥对生成、签名、验证，SHA-512 预哈希 |
| PyOCD 烧录 | SWD 调试探针固件烧录，支持 CMSIS Pack 目标 |
| 增量差分 | bsdiff4 / HPatchLite 双引擎，OTA 增量更新 |
| HTML UI 提取 | Playwright 截图提取 LVGL 嵌入式显示资源 |
| 支付宝沙箱 | IoT 售货机支付集成，自定义串口协议与 STM32 通信 |

## 二、技术栈

| 层次 | 技术选型 |
|---|---|
| 编程语言 | Python 3 |
| GUI 框架 | PyQt6 |
| UI 组件库 | qfluentwidgets（Fluent Design 风格） |
| 串口通信 | pyserial |
| 终端仿真 | pyte（VT100 解析） |
| 固件传输 | ymodem |
| 加密库 | pycryptodome（AES, HMAC, Ed25519） |
| 调试烧录 | pyocd（ARM Cortex SWD） |
| 增量差分 | bsdiff4, hpatchlite |
| 浏览器自动化 | playwright（Chromium headless） |

## 三、项目结构

```
host_computer_project/
├── main.py                         # 应用入口、窗口创建
├── serial_tools/                   # 串口终端 + YMODEM 传输
│   └── serial_interface.py
├── pyocd_tools/                    # PyOCD SWD 烧录
│   └── pyocd_interface.py
├── aes_tools/                      # AES 加解密 + HKDF
│   └── aes_interface.py
├── bsdiff_tools/                   # bsdiff4 增量差分
│   └── bsdiff_interface.py
├── hpatchlite_tools/               # HPatchLite 增量差分
│   ├── hpatchlite_interface.py
│   ├── hdiffi.exe
│   └── hpatchi.exe
├── firmware_header_tools/          # 固件打包流水线（核心）
│   └── header_interface.py
├── ed25519_tools/                  # Ed25519 数字签名
│   └── ed25519_interface.py
├── html_ui_extract_tools/          # LVGL 资源提取
│   ├── html_ui_extract_interface.py
│   ├── lvgl/                       # 提取后的 LVGL 图标资源
│   └── lvgl_resources/             # 提取后的 LVGL 图像资源
├── alipay_sandbox_tools/           # 支付宝沙箱支付集成
│   └── alipay_sandbox_interface.py
└── settings/                       # 应用设置界面
    ├── config.py
    ├── setting_interface.py
    ├── config/
    │   └── config.json
    └── resource/
        ├── i18n/                   # 国际化文件（zh_CN, zh_HK）
        ├── images/                 # 应用图标与 Logo
        └── qss/                    # 主题样式（dark / light）
```

## 四、应用架构

### 4.1 FluentWindow 侧边栏导航

主窗口采用 `FluentWindow` 侧边栏导航模式，10 个功能页面各对应一个独立模块：

```python
class Window(FluentWindow):
    def __init__(self):
        self.serialInterface = SerialTabWidget()
        self.pyocdInterface = Pyocd_Tools_Widget()
        self.aesInterface = AES_Tools_Widget()
        self.bsdiffInterface = BSDiff_Tools_Widget()
        self.hpatchliteInterface = HPatchLite_Tools_Widget()
        self.firmwareHeaderInterface = FirmwareHeader_Widget()
        self.ed25519Interface = Ed25519_Widget()
        self.htmlUIExtractInterface = HTML_UI_Extract_Widget()
        self.alipaySandboxInterface = AlipaySandbox_Widget()
        self.settingInterface = SettingInterface(self)
```

### 4.2 启动流程

1. DPI 缩放初始化
2. 国际化翻译加载（zh_CN, zh_HK, en_US）
3. 闪屏显示
4. 主窗口创建与导航注册

### 4.3 QThread + pyqtSignal 异步模式

所有耗时操作采用统一的异步工作模式，确保 GUI 主线程不被阻塞：

```python
class XxxThread(QThread):
    progress_signal = pyqtSignal(int, str)   # 进度回调
    finished_signal = pyqtSignal(bool, str)  # 完成通知
    def run(self):
        # 耗时操作
        self.progress_signal.emit(percent, message)
        self.finished_signal.emit(success, result)
```

## 五、固件打包流水线（核心）

整个工具套件最核心的功能，将原始固件经过完整的安全处理链路，生成可部署的 `.iap.bin` 固件包。

### 5.1 固件头结构（64 字节）

| 偏移 | 字段 | 大小 | 说明 |
|---|---|---|---|
| 0x00 | magic | 4B | `IAP\x01` 魔数 |
| 0x04 | header_version | 1B | 头版本号 |
| 0x05 | firmware_version_major | 1B | 固件主版本 |
| 0x06 | firmware_version_minor | 1B | 固件次版本 |
| 0x07 | firmware_version_patch | 1B | 固件补丁版本 |
| 0x08 | total_payload_size | 4B | 加密后载荷总大小 |
| 0x0C | image_type | 1B | 0x01=App, 0x02=Bootloader, 0x03=Resource |
| 0x0D | encryption_algorithm | 1B | 0x00=None, 0x01=AES-256-CBC, 0x02=ECB, 0x03=CTR |
| 0x0E | signature_algorithm | 1B | 0x00=None, 0x01=Ed25519 |
| 0x0F | hardware_compatibility | 1B | 硬件兼容性标识 |
| 0x10 | security_counter | 4B | 安全计数器（防回滚） |
| 0x14 | build_timestamp | 4B | 构建时间戳 |
| 0x18 | reserved | 5B | 保留字段 |
| 0x1D | header_checksum | 32B | HMAC-SHA256 校验（使用 DevKey） |

### 5.2 最终固件包格式

| 区域 | 大小 | 说明 |
|---|---|---|
| Header | 64 bytes | 魔术字、版本、加密/签名算法等 |
| DynamicSalt | 16 bytes | HKDF 盐值，每固件独立 |
| IV | 16 bytes | AES 初始化向量 |
| Ciphertext | N bytes | AES-256 加密的固件 + 追加的 SHA-256 |
| Signature | 64 bytes | Ed25519 数字签名 |

### 5.3 打包线程核心逻辑

```python
class PackageThread(QThread):
    def run(self):
        # 1. 读取原始固件
        firmware_data = open(firmware_path, 'rb').read()
        # 2. 追加 SHA-256 哈希用于完整性校验
        firmware_hash = SHA256.new(firmware_data).digest()
        data_to_encrypt = firmware_data + firmware_hash
        # 3. AES-256 加密（密钥由 HKDF 派生）
        cipher = AES.new(aes_key, AES.MODE_CBC, iv=iv)
        ciphertext = cipher.encrypt(pad(data_to_encrypt, AES.block_size))
        # 4. 构建固件头
        header = FirmwareHeader(...)
        header.header_checksum = HMAC.new(dev_key, header_prefix, SHA256).digest()
        # 5. Ed25519 签名（对 header + salt + iv + ciphertext）
        signer = eddsa.new(private_key, 'rfc8032')
        signature = signer.sign(payload)
        # 6. 组装最终包
        package = header_bytes + dynamic_salt + iv + ciphertext + signature
```

加密前先追加 SHA-256 哈希是关键设计。解密时，STM32 端先解密去除填充，再验证末尾 32 字节 SHA-256 是否与解密数据的前部匹配，实现**解密即校验** 的双重保障。

### 5.4 可视化对比

打包完成后，`PackCompareDialog` 用颜色编码展示固件包各区域：

| 颜色 | 区域 |
|---|---|
| 蓝色 | Header（64B） |
| 红色 | DynamicSalt（16B） |
| 紫色 | IV（16B） |
| 绿色 | Ciphertext（变长） |
| 橙色 | Signature（64B） |

## 六、HKDF 设备绑定密钥派生

安全体系的核心机制，确保固件包只能由目标设备解密。

### 6.1 两阶段 HKDF

```python
def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract: 从输入密钥材料提取固定长度的伪随机密钥"""
    prk = HMAC.new(salt, ikm, digestmod=SHA256).digest()
    return prk

def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand: 将伪随机密钥扩展为所需长度的输出密钥材料"""
    hash_len = SHA256.digest_size
    n = (length + hash_len - 1) // hash_len
    okm = b''
    t = b''
    for i in range(1, n + 1):
        t = HMAC.new(prk, t + info + bytes([i]), digestmod=SHA256).digest()
        okm += t
    return okm[:length]
```

### 6.2 密钥派生链路

1. **Extract 阶段**：`HMAC-SHA256(salt=DynamicSalt, ikm=DevKey)` → PRK
2. **Expand 阶段**：`HMAC-SHA256(PRK, info=UID || counter)` → 32 字节 AES 密钥

三个安全要素的角色：

| 要素 | 来源 | 作用 |
|---|---|---|
| DevKey (128-bit) | STM32 OTP 熔丝 | 设备密钥，不可读取 |
| UID (96-bit) | STM32 芯片唯一 ID | HKDF-Expand 的 info 参数，实现密钥与芯片绑定 |
| DynamicSalt (128-bit) | 每固件版本随机生成 | 确保同设备不同固件版本产生不同加密密钥 |

三个要素缺一不可：DevKey 保证只有合法设备能解密，UID 保证固件包只能由特定芯片解密，DynamicSalt 保证同一设备的每次升级使用不同密钥。这就是**设备绑定加密** 的核心原理。

## 七、AES-256 加密模块

### 7.1 支持的加密模式

| 模式 | 特点 | 适用场景 |
|---|---|---|
| CBC | 需 IV，并行解密 | 默认推荐 |
| ECB | 无 IV，相同明文→相同密文 | 不推荐（仅兼容旧方案） |
| CTR | 流式加密，无需填充 | 高性能场景 |
| CFB | 流式加密，自同步 | 误码容忍场景 |
| OFB | 流式加密，无错误传播 | 噪声信道场景 |

### 7.2 加密流程

```python
# 加密前先追加 SHA-256 哈希
firmware_hash = SHA256.new(firmware_data).digest()
data_to_encrypt = firmware_data + firmware_hash  # 原始固件 + 32字节哈希
# PKCS7 填充后加密
cipher = AES.new(key, AES.MODE_CBC, iv=iv)
ciphertext = cipher.encrypt(pad(data_to_encrypt, AES.block_size))
```

### 7.3 解密与校验

```python
# 解密
cipher = AES.new(key, AES.MODE_CBC, iv=iv)
plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
# 分离固件和哈希
firmware = plaintext[:-32]
embedded_hash = plaintext[-32:]
# 校验完整性
computed_hash = SHA256.new(firmware).digest()
assert computed_hash == embedded_hash, "固件完整性校验失败"
```

## 八、Ed25519 数字签名

### 8.1 签名流程

```python
# 密钥对生成
key = ECC.generate(curve='ed25519')
# 签名（SHA-512 预哈希，RFC8032 变体）
signer = eddsa.new(key, 'rfc8032')
signature = signer.sign(data)  # 输出 64 字节签名
# 验证
verifier = eddsa.new(key, 'rfc8032')
verifier.verify(signature, data)
```

### 8.2 密钥格式支持

| 格式 | 用途 |
|---|---|
| PEM | 标准存储格式 |
| 原始字节 | 嵌入式端使用 |
| 十六进制 | 调试显示 |
| C 数组 | 直接嵌入固件源码 |

Ed25519 的公钥只有 32 字节，签名只有 64 字节，非常适合资源受限的嵌入式场景。相比 RSA-2048（256 字节签名），Ed25519 在安全性和效率上都有显著优势。

## 九、串口终端与 YMODEM 传输

### 9.1 VT100 终端仿真

基于 pyte 实现 VT100 终端解析：

```python
class PyteTerminal:
    def __init__(self, cols=80, rows=24):
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
    def feed(self, data):
        self.stream.feed(data)  # 解析 ANSI 转义序列
    def get_display(self):
        return self.screen.display  # 获取渲染后的文本行
```

`TerminalTextEdit` 实现了完整的终端模式：支持光标定位、颜色渲染（使用格式化缓存优化性能）、滚动区域管理。

### 9.2 YMODEM 固件传输

```python
class YModem_Send_Thread(QThread):
    def run(self):
        def read(size, timeout=3):
            data = self.serial_port.read(size)
            return data
        def write(data, timeout=3):
            self.serial_port.write(data)
            return len(data)
        cli = ModemSocket(read, write)
        result = cli.send(self.file_paths, callback=ymodem_callback)
```

### 9.3 调试器自动发现

串口模块通过 USB VID/PID 自动识别 JLink/STLink/DAPLink，并与 PyOCD 模块联动，减少用户手动配置。

## 十、PyOCD SWD 烧录

通过 ARM SWD 接口直接烧录 Flash，不经过 Bootloader：

```python
class Pyocd_Program_Thread(QThread):
    def run(self):
        session = ConnectHelper.session_with_chosen_probe(
            target=self.target,
            connect_mode=self.connect_mode,  # halt/attach/pre-reset
        )
        with session:
            board = session.board
            flash = board.flash
            flash.build_image()
            flash.program(
                self.firmware_data,
                base_address=self.base_address,
                erase=self.erase_mode,  # chip/sector/no-erase
                trust_crc=self.trust_crc,
            )
```

| 特性 | 说明 |
|---|---|
| 探针自动刷新 | 5 秒间隔，变更检测 |
| CMSIS Pack 支持 | 扫描 .pack/.pdsc 获取目标 MCU 定义 |
| 默认目标 | `stm32f407vgtx` |
| 擦除模式 | 全片擦除 / 扇区擦除 / 不擦除 |
| 连接模式 | halt / attach / pre-reset |

## 十一、双差分引擎

同时集成 bsdiff4 和 HPatchLite 两种差分引擎，为不同场景提供选择。

### 11.1 引擎对比

| 特性 | bsdiff4 | HPatchLite |
|---|---|---|
| 类型 | Python 库 | 外部可执行文件 |
| 压缩算法 | bzip2 | tuz / zlib / lzma / lzma2 |
| 集成方式 | `import bsdiff4` | 子进程调用 |
| 并行支持 | 无 | 支持多线程 |
| 原地补丁 | 不支持 | 支持 |
| 适用场景 | 简单快速 | 高级选项、嵌入式端兼容 |

### 11.2 差分升级效果

假设旧固件 384KB，新固件 386KB，差分文件可能只有 5-20KB。在带宽受限的场景下，差分升级能显著减少传输时间和流量费用。

## 十二、支付宝沙箱与自定义串口协议

### 12.1 帧格式

```
0xAA 0x55 | CMD(1B) | LEN(2B, 大端序) | DATA(NB) | 0x0D 0x0A
```

```python
def _build_frame(self, cmd, data):
    header = bytes([0xAA, 0x55])
    tail = bytes([0x0D, 0x0A])
    length = struct.pack('>H', len(data))
    return header + bytes([cmd]) + length + data + tail
```

### 12.2 命令集

| 方向 | CMD | 说明 |
|---|---|---|
| PC→STM32 | 0x01 | 发送二维码 URL |
| PC→STM32 | 0x02 | 支付状态通知 |
| PC→STM32 | 0x03 | 发送交易号 |
| PC→STM32 | 0x04 | 心跳响应 |
| STM32→PC | 0x81 | 请求二维码 |
| STM32→PC | 0x82 | 查询支付状态 |
| STM32→PC | 0x83 | 关闭订单 |
| STM32→PC | 0x84 | 心跳 |

命令编码规则：`0x0x` 为 PC→STM32，`0x8x` 为 STM32→PC，最高位区分方向。接收线程 `SerialReceiveThread` 解析 `0xAA 0x55` 帧头，提取命令码和数据载荷。

## 十三、HTML UI 提取（LVGL 资源）

通过 Playwright（Chromium headless）自动截图，将 HTML/CSS 设计稿转换为 LVGL 嵌入式显示资源：

1. 加载 HTML 文件到 headless 浏览器
2. 截取指定区域/元素
3. 转换为 C 数组格式的图像数据
4. 输出为 LVGL 兼容的 `.c` / `.h` 文件

## 十四、安全链路全景

**上位机构建端：**

1. 原始固件 → SHA-256 哈希追加
2. → HKDF 派生 AES 密钥（DynamicSalt + DevKey + UID）
3. → AES-256 加密
4. → 构建 Header + HMAC-SHA256 校验
5. → Ed25519 签名
6. → `.iap.bin`

**设备端验证（STM32 Bootloader）：**

1. `.iap.bin` → HMAC-SHA256 验证 Header（DevKey）
2. → 硬件兼容检查
3. → 防回滚检查（安全计数器）
4. → HKDF 派生 AES 密钥（Salt + DevKey + UID）
5. → AES 解密 → 写入 Flash
6. → SHA-512 流式哈希 → Ed25519 签名验证
7. → 回读 Flash SHA-256 校验

**安全分层防御：**

| 层 | 机制 | 解决的问题 |
|---|---|---|
| 真实性 | Ed25519 签名 | 谁签的？ |
| 头完整性 | HMAC-SHA256 | 头被篡改？ |
| 机密性 | AES-256 加密 | 内容保密 |
| 载荷完整性 | SHA-256 哈希 | 数据正确？ |
| 防回滚 | Security Counter | 旧版本？ |
| 密钥隔离 | HKDF 派生 | 同设备不同密钥 |
| 芯片绑定 | UID 绑定 | 密钥与芯片关联 |

## 十五、快速开始

### 15.1 环境要求

- Python 3.10+
- Windows / Linux / macOS

### 15.2 安装依赖

```bash
pip install PyQt6 PyQt6-Fluent-Widgets pyserial pyte ymodem pycryptodome pyocd bsdiff4 playwright
```

> HPatchLite 模块依赖同目录下的 `hdiffi.exe` / `hpatchi.exe`，无需额外安装。
> Playwright 首次使用需下载浏览器：`playwright install chromium`

### 15.3 运行

```bash
python main.py
```

---

## 相关项目

- [STM32F407 安全 Bootloader 设计](https://lingjia007.github.io/Hugo_Web/p/stm32f407-secure-bootloader/) —— 设备端的 A/B 双分区、加密签名与多渠道升级机制

## 作者

**Lingsir007** —— [GitHub](https://github.com/Lingjia007) | [博客](https://lingjia007.github.io/Hugo_Web)

如果这个项目帮助到了您，可以在应用内点击作者头像支持一下🥤
