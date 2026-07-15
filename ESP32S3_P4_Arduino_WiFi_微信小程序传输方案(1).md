# ESP32-S3/P4 Arduino 通用 Wi-Fi 传输方案（面向微信小程序）

## 1. 目标

实现一套适用于 `ESP32-S3 / ESP32-P4` 的 Arduino 端通用 Wi‑Fi 数据传输方案，最终支持以下两种场景：

1. 手机与设备处于同一路由器局域网下进行数据传输
2. 手机开启热点，设备连接手机热点后进行数据传输

目标通信对象为 `微信小程序`。

---

## 2. 先说关键结论

- `ESP32-S3` 可以直接使用 Arduino 的 `WiFi.h` 进行 Wi‑Fi 联网和数据传输
- `ESP32-P4` 不能简单等同于 `ESP32-S3` 的联网写法，因此不能假设它可以直接原样使用 `WiFi.h`
- 如果希望做成 `S3/P4 通用代码`，正确做法不是强行统一底层驱动，而是：
  - 统一 `协议层`
  - 统一 `业务层`
  - 将 `联网接入层` 做成可替换模块

也就是说，真正能通用的是：

- 数据协议
- HTTP 接口
- WebSocket 实时传输逻辑
- JSON 消息解析
- 业务命令分发

而不一定是最底层的联网驱动代码。

---

## 3. 推荐总体方案

对于“微信小程序 + 局域网 / 手机热点”这个场景，推荐采用：

- `HTTP`：用于状态查询、简单配置、单次命令
- `WebSocket`：用于实时双向通信
- `JSON`：作为统一的数据格式

这是当前最适合做控制、状态上报、调试联通性验证的一套方案。

---

## 4. 为什么推荐这套方案

优点如下：

- 局域网和手机热点本质上都是“设备与手机在同一子网中”，代码逻辑基本一致
- `WebSocket` 很适合微信小程序做实时控制和状态监听
- `HTTP` 适合做设备信息查询和简单命令接口
- 上层协议可以被 `ESP32-S3` 和 `ESP32-P4` 共用
- 后续如果要切换到底层网络模块，只需要改联网适配层

---

## 5. 网络模式建议

建议你把主通信模式确定为：

`ESP 作为 STA 连接现有 Wi‑Fi 网络`

这个“现有 Wi‑Fi 网络”包括：

- 家用路由器
- 手机热点

也就是说：

- 当手机和 ESP 都连到家里路由器时，可以通信
- 当手机开启热点，ESP 连到手机热点时，也可以通信

这两种场景在程序设计上本质一致，不需要分成两套传输协议。

---

## 6. 一个很容易混淆的点

需要区分下面两种情况：

### 6.1 手机热点

这是指：

- 手机自己开启热点
- ESP 作为客户端连接这个热点

此时 ESP 仍然工作在：

- `WIFI_STA`

### 6.2 ESP 自己开热点

这是指：

- ESP 启动 `SoftAP`
- 手机连接 ESP 提供的热点

这是另一种工作模式，适合：

- 首次配网
- 没有现成路由器时的兜底接入

但不建议把它作为你的主通信模式。

---

## 7. 推荐的软件架构

建议把工程拆成 4 层：

### 7.1 联网适配层 `NetAdapter`

负责：

- 连接 Wi‑Fi
- 断线重连
- 查询 IP
- 查询连接状态

建议定义统一接口，例如：

```cpp
class INetAdapter {
public:
  virtual bool connect() = 0;
  virtual bool isConnected() = 0;
  virtual String localIP() = 0;
  virtual void loop() = 0;
};
```

然后分别实现：

- `NetAdapter_S3`
- `NetAdapter_P4`

### 7.2 HTTP 服务层 `HttpApi`

负责：

- `GET /info`：查询设备信息
- `POST /cmd`：发送简单命令

### 7.3 WebSocket 实时通道 `WsChannel`

负责：

- 实时状态上报
- 实时控制命令下发
- 消息确认

### 7.4 协议层 `Protocol`

负责：

- JSON 编解码
- 消息字段统一
- 命令与状态的数据结构定义

---

## 8. 推荐的消息格式

建议统一使用 JSON 消息结构。

### 8.1 状态上报

```json
{
  "type": "telemetry",
  "seq": 12,
  "data": {
    "temp": 25.4,
    "relay": 1
  }
}
```

### 8.2 控制命令

```json
{
  "type": "control",
  "seq": 13,
  "data": {
    "relay": 0
  }
}
```

### 8.3 应答消息

```json
{
  "type": "ack",
  "seq": 13,
  "ok": true
}
```

推荐保留这些字段：

- `type`：消息类型
- `seq`：消息序号
- `data`：具体业务数据
- `ok`：结果标志
- `msg`：错误或说明信息

---

## 9. Arduino 端推荐接口设计

建议对外暴露：

- `GET /info`
- `POST /cmd`
- `WebSocket :81`

例如：

- `http://设备IP/info`
- `http://设备IP/cmd`
- `ws://设备IP:81`

---

## 10. ESP32-S3 端最小可用代码骨架

下面是一份适合先跑通链路的基础示例。

```cpp
#include <WiFi.h>
#include <WebServer.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>

WebServer httpServer(80);
WebSocketsServer wsServer(81);

struct WifiProfile {
  const char* ssid;
  const char* pass;
};

WifiProfile wifiList[] = {
  {"HomeWiFi", "12345678"},
  {"PhoneHotspot", "87654321"}
};

bool connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  for (auto &item : wifiList) {
    WiFi.begin(item.ssid, item.pass);
    unsigned long start = millis();

    while (millis() - start < 10000) {
      if (WiFi.status() == WL_CONNECTED) {
        return true;
      }
      delay(300);
    }

    WiFi.disconnect(true, true);
    delay(300);
  }
  return false;
}

void handleInfo() {
  StaticJsonDocument<256> doc;
  doc["device"] = "esp32";
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();

  String out;
  serializeJson(doc, out);
  httpServer.send(200, "application/json", out);
}

void onWsEvent(uint8_t num, WStype_t type, uint8_t *payload, size_t len) {
  if (type == WStype_TEXT) {
    String msg = (char*)payload;

    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, msg) == DeserializationError::Ok) {
      const char* typeStr = doc["type"];
      if (strcmp(typeStr, "control") == 0) {
        // 在这里处理控制命令
      }
    }

    wsServer.sendTXT(num, "{\"type\":\"ack\",\"ok\":true}");
  }
}

void setup() {
  Serial.begin(115200);

  connectWifi();

  httpServer.on("/info", HTTP_GET, handleInfo);
  httpServer.begin();

  wsServer.begin();
  wsServer.onEvent(onWsEvent);
}

void loop() {
  httpServer.handleClient();
  wsServer.loop();

  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }
}
```

这份代码的作用是：

- 自动尝试连接多个 Wi‑Fi
- 启动 HTTP 服务
- 启动 WebSocket 服务
- 支持微信小程序向设备发送控制消息
- 支持设备向小程序回发确认消息

---

## 11. 微信小程序端的基本连接方式

小程序侧的核心思路是：

1. 知道设备 IP 地址
2. 通过 WebSocket 与设备建立连接

基础示例：

```javascript
const deviceIp = '192.168.31.88'

const socket = wx.connectSocket({
  url: `ws://${deviceIp}:81`,
  success() {
    console.log('socket connecting')
  }
})

socket.onOpen(() => {
  socket.send({
    data: JSON.stringify({
      type: 'control',
      seq: 1,
      data: { relay: 1 }
    })
  })
})

socket.onMessage((res) => {
  const msg = JSON.parse(res.data)
  console.log('recv', msg)
})
```

---

## 12. 小程序端的实际工作流建议

建议小程序这样组织：

### 12.1 首次连接

- 手动输入设备 IP
- 或通过扫码录入设备地址

### 12.2 建立连接

- 先请求 `HTTP /info`
- 再连接 `WebSocket`

### 12.3 实时通信

- 控制命令通过 WebSocket 发出
- 设备状态通过 WebSocket 推送回来

这样做的好处是：

- 调试简单
- 出错时容易定位
- 后续扩展方便

---

## 13. 关于设备发现

局域网通信里，设备发现是一个单独问题。

你有几种选择：

### 13.1 手动输入 IP

最简单，最适合最初开发验证。

### 13.2 固定 DHCP 或路由器绑定 IP

适合家用路由器场景。

### 13.3 mDNS

例如通过主机名访问：

`esp-device.local`

但小程序环境下对这类访问方式是否稳定可用，需要你实际测试。

所以建议开发初期：

- 优先用手动输入 IP

---

## 14. 关于 ESP32-P4 的处理方式

如果你的目标是 `ESP32-S3 / P4` 共用一套代码，那么推荐策略是：

### 14.1 统一上层

共用：

- HTTP 服务
- WebSocket 服务
- JSON 协议
- 业务控制逻辑

### 14.2 替换底层联网适配

`S3` 使用：

- `WiFi.h`

`P4` 使用：

- 板级实际提供的联网方案对应实现

对业务层来说，只依赖：

```cpp
net.connect();
net.isConnected();
net.localIP();
net.loop();
```

这样就能把“通用”真正落到代码结构上。

---

## 15. 推荐开发顺序

最稳妥的落地顺序如下：

### 第一步：先用 ESP32-S3 跑通

先验证：

- 连家里路由器
- 连手机热点
- 小程序通过 WebSocket 控制设备

### 第二步：抽象联网接口

把 Wi‑Fi 连接逻辑抽到：

- `INetAdapter`

### 第三步：再适配 P4

只替换底层联网接入实现，不改协议层和业务层。

---

## 16. 这套方案的优点

- 架构清晰
- 便于调试
- 局域网和手机热点兼容
- S3 与 P4 可以最大程度共用上层代码
- 后续方便扩展到更多命令和数据类型

---

## 17. 需要特别注意的问题

这里有一个很关键的现实问题：

“技术上能通” 不等于 “微信小程序发布后一定允许这样用”。

原因是微信小程序对以下内容存在平台规则和限制：

- HTTP 请求目标
- WebSocket 连接目标
- 域名/IP 使用方式
- 局域网访问能力
- 审核与上线要求

因此建议：

- 开发调试阶段先用局域网直连方案验证链路
- 如果要正式发布上线，提前核实当前微信小程序平台对局域网 IP、Socket、域名配置的最新要求

这一步必须尽早确认，不要等全部功能写完再处理。

---

## 18. 如何让小程序过滤掉无关请求，只识别 ESP32

这里先澄清一个关键点：

`微信小程序不能像局域网里的 HTTP 服务器那样，被动监听别人发来的 POST 请求。`

小程序通常是客户端，它能做的是：

- 主动向 ESP32 发起 HTTP 请求
- 主动连接 ESP32 的 WebSocket
- 如果使用 UDP 发现设备，则在小程序侧接收发现包后再决定是否连接

因此，“过滤掉无关的 POST 请求，只监听 ESP32 的请求” 这件事，不应该理解为：

- 让小程序开放一个接口，等待局域网内其他设备向它 POST 数据

而应该理解为：

- 小程序只主动连接目标 ESP32
- 小程序只接受来自目标 ESP32 的数据
- 小程序对收到的数据再做一次身份校验

### 18.1 正确的思路

推荐把过滤分成两层：

#### 第一层：连接前过滤

在真正通信之前，先判断“这个设备是不是我的 ESP32”。

可以采用以下方式：

- 手动输入设备 IP
- 让用户从扫描结果中选择设备
- 使用 UDP 广播做局域网发现

如果使用 UDP 广播，建议广播包中加入固定识别字段，例如：

```json
{
  "magic": "ESP32_DISCOVERY_V1",
  "vendor": "your_brand",
  "deviceType": "esp32",
  "deviceId": "esp32s3_001",
  "name": "living_room_node",
  "wsPort": 81,
  "httpPort": 80
}
```

这样小程序发现设备后，可以先判断：

- `magic` 是否正确
- `vendor` 是否正确
- `deviceType` 是否是目标设备
- `deviceId` 是否在允许列表内

不满足条件的设备直接忽略。

#### 第二层：连接后过滤

即使已经连接到了目标 IP，也不要默认所有消息都可信。

建议每条消息都带上：

- `deviceId`
- `token`
- `timestamp`
- `nonce`
- `sign`

小程序收到消息后再次校验：

1. `deviceId` 是否等于当前选中的设备
2. `token` 是否匹配
3. `timestamp` 是否在有效时间窗口内
4. `sign` 是否验证通过

只要有任意一项不通过，就直接丢弃该消息。

### 18.2 为什么不建议 ESP32 主动 POST 到小程序

不建议采用：

- `ESP32 -> HTTP POST -> 小程序`

原因是：

- 小程序本身不适合做局域网里的被动 HTTP 服务端
- 这种架构不符合小程序常见的网络模型
- 也不利于你做“只接收目标设备数据”的过滤

更推荐的结构是：

- `小程序 -> HTTP -> ESP32`
- `小程序 -> WebSocket -> ESP32`

也就是始终由小程序作为连接发起方。

这样天然就规避了“局域网里别的设备乱 POST 给小程序”的问题。

### 18.3 最推荐的实现方式

对于你的场景，推荐采用：

1. UDP 做设备发现
2. 小程序只显示符合标识规则的 ESP32
3. 用户选择一个设备
4. 小程序仅连接该设备的固定地址和固定端口
5. 之后所有业务通信走 WebSocket
6. 每条业务消息都校验设备身份

### 18.4 固定路径和固定端口

为了进一步降低误连接风险，建议固定通信入口：

- HTTP 状态查询：`http://<ip>/esp32/info`
- HTTP 控制接口：`http://<ip>/esp32/cmd`
- WebSocket 通道：`ws://<ip>:81/esp32`

这样即使同一局域网中还有别的 HTTP 服务，也不会轻易误连。

### 18.5 推荐的消息格式

建议 ESP32 发给小程序的每条消息都使用统一结构：

```json
{
  "type": "telemetry",
  "deviceId": "esp32s3_001",
  "ts": 1720600000,
  "nonce": "a8f3c1",
  "token": "demo-token",
  "sign": "xxxxx",
  "data": {
    "temp": 26.5
  }
}
```

小程序在处理前，先做如下判断：

1. `deviceId` 是否匹配当前设备
2. `token` 是否正确
3. `ts` 是否超时
4. `sign` 是否校验通过

全部通过后才交给业务逻辑处理。

### 18.6 小程序端最实用的过滤策略

建议至少做以下三层过滤：

- `IP 过滤`
  - 小程序只访问用户确认过的那个设备 IP
- `路径过滤`
  - 小程序只使用约定好的固定路径和端口
- `身份过滤`
  - 每条消息都校验 `deviceId + token`

如果需要更高安全性，可以再增加：

- `消息签名`
- `时间戳过期校验`
- `随机数 nonce 防重放`

### 18.7 最终理解

所以，你真正要做的不是：

- “让小程序监听局域网里所有 POST，再从中筛掉不是 ESP32 的请求”

而是：

- “让小程序只主动连接目标 ESP32，并且只处理通过身份校验的消息”

这是更符合微信小程序能力边界、也更稳定可靠的实现方式。

---

## 19. 最终建议

如果你要做一个真正可维护、可扩展的 `ESP32-S3/P4 Arduino 通用 Wi‑Fi 传输方案`，最推荐的路径是：

1. 用 `ESP32-S3` 先跑通 Wi‑Fi、HTTP、WebSocket、小程序联调
2. 将联网部分抽象成适配层
3. 将协议与业务逻辑写成与芯片无关的通用模块
4. 再为 `ESP32-P4` 补充对应的联网实现

核心原则是：

`底层联网适配可替换，上层协议与业务保持统一`

这才是最适合你这个项目目标的“通用代码”方案。
