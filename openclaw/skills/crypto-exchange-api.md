# 加密货币交易所 API 参考技能

> **用途**: 所有加密货币交易项目的通用API知识库（CEX + DEX + 衍生品）
> **更新日期**: 2026-01-19
> **维护**: 根据实测和官方文档更新

---

## 📑 目录

- [中心化交易所 (CEX)](#-中心化交易所-cex)
- [永续合约 DEX](#-永续合约-dex-perp-dex)
- [期权与衍生品平台](#-期权与衍生品平台-options--derivatives)
- [预测市场](#-预测市场-prediction-markets)
- [现货 DEX & 聚合器](#-现货-dex--聚合器-spot-dex--aggregator)
- [链上数据与价格喂价](#-链上数据与价格喂价-on-chain-data)

---

## 🏦 中心化交易所 (CEX)

## 📋 快速速查表

| 交易所 | 现货端点 | 合约端点 | Symbol格式 | 响应类型 |
|--------|----------|----------|------------|----------|
| **Binance** | `/api/v3/exchangeInfo` | `/fapi/v1/exchangeInfo` | `RIVERUSDT` | dict.symbols |
| **OKX** | `?instType=SPOT` | `?instType=SWAP` | `RIVER-USDT` | dict.data[] |
| **Gate.io** | `/api/v4/spot/currency_pairs` | `/api/v4/futures/usdt/contracts` | `RIVER_USDT` | **直接返回list** |
| **Bitget** | `/api/v2/spot/public/symbols` | `/api/v2/mix/market/tickers?productType=USDT-FUTURES` | `RIVERUSDT` | dict.data |
| **Bybit** | `/v5/market/tickers?category=spot` | `/v5/market/tickers?category=linear` | `RIVERUSDT` | dict.result.list |

---

## 🔗 官方文档地址

### Binance (币安)
- **现货**: https://binance-docs.github.io/apidocs/spot/cn/
- **合约**: https://binance-docs.github.io/apidocs/futures/cn/
- **API版本**: V3 (Spot) / V1 (Futures)
- **稳定性**: ⭐⭐⭐⭐⭐ (行业基准)

### OKX (欧易)
- **主文档**: https://www.okx.com/docs-v5/zh/
- **API版本**: V5 (统一)
- **稳定性**: ⭐⭐⭐⭐ (结构统一)

### Bybit
- **V5文档**: https://bybit-exchange.github.io/docs/v5/intro
- **GitHub**: https://github.com/bybit-exchange
- **API版本**: V5 (综合)
- **稳定性**: ⭐⭐⭐⭐ (演进快)

### Gate.io (芝麻开门)
- **开发文档**: https://www.gate.io/docs/developers/apiv4/zh/
- **API版本**: V4
- **稳定性**: ⭐⭐⭐ (参数较繁琐)

### Bitget
- **主文档**: https://www.bitget.com/api-doc/common/intro
- **现货文档**: https://www.bitget.com/api-doc/spot/intro
- **合约文档**: https://www.bitget.com/api-doc/mix/intro
- **API版本**: V2 (当前最新稳定版)
- **⚠️ 重要**: **没有V4 API**，V3仅适用于统一交易账户（UTA）
- **V1状态**: 已废弃（2025年11月28日停用）
- **稳定性**: ⭐⭐⭐⭐ (稳定版)
- **WebSocket**: `wss://ws.bitget.com/v2/ws/public`

---

## 🎯 核心端点详情

### 1. Binance

#### 现货交易对查询
```http
GET https://api.binance.com/api/v3/exchangeInfo
```
- **响应结构**:
  ```json
  {
    "symbols": [
      {
        "symbol": "RIVERUSDT",
        "status": "TRADING",
        "baseAsset": "RIVER",
        "quoteAsset": "USDT"
      }
    ]
  }
  ```

#### 合约交易对查询
```http
GET https://fapi.binance.com/fapi/v1/exchangeInfo
```
- **响应结构**: 同现货，但返回合约交易对

---

### 2. OKX

#### 现货交易对查询
```http
GET https://www.okx.com/api/v5/public/instruments?instType=SPOT
```
- **响应结构**:
  ```json
  {
    "code": "0",
    "msg": "",
    "data": [
      {
        "instId": "RIVER-USDT",
        "baseCcy": "RIVER",
        "quoteCcy": "USDT",
        "state": "live",
        "trading": "true"
      }
    ]
  }
  ```

#### 合约交易对查询
```http
GET https://www.okx.com/api/v5/public/instruments?instType=SWAP
```
- **Symbol格式**: `RIVER-USDT-SWAP` (永续合约)

---

### 3. Gate.io ⚠️ 特殊注意

#### 现货交易对查询
```http
GET https://api.gateio.ws/api/v4/spot/currency_pairs
```
- **⚠️ 重要**: API **直接返回列表**，不是包含 `pairs` 键的字典
- **响应结构**:
  ```json
  [
    {
      "id": "RIVER_USDT",
      "base": "RIVER",
      "quote": "USDT",
      "trade_status": "tradable"
    }
  ]
  ```

#### 合约交易对查询
```http
GET https://api.gateio.ws/api/v4/futures/usdt/contracts
```
- **⚠️ 重要**:
  - API **直接返回列表**
  - **没有** `contract_type` 字段（USDT合约默认都是永续）
  - Symbol格式: `RIVER_USDT`
- **响应结构**:
  ```json
  [
    {
      "name": "RIVER_USDT",
      "status": "trading",
      "quanto_multiplier": "0.01"
    }
  ]
  ```

---

### 4. Bitget ⚡ V2 API (当前最新版本)

#### ⚠️ API版本说明
- **V2**: 当前最新稳定版本 ✅ (推荐使用)
- **V3**: 仅适用于统一交易账户（UTA）用户
- **V1**: 已废弃（2025年11月28日停用）❌
- **注意**: **没有V4 API**

#### 现货交易对查询
```http
GET https://api.bitget.com/api/v2/spot/public/symbols
```
- **响应结构**:
  ```json
  {
    "code": "00000",
    "msg": "success",
    "data": [
      {
        "symbol": "RIVERUSDT",
        "baseCoin": "RIVER",
        "quoteCoin": "USDT",
        "status": "online"
      }
    ]
  }
  ```

#### 合约交易对查询
```http
GET https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES
```
- **productType**: 必须是 `USDT-FUTURES`
- **响应结构**:
  ```json
  {
    "code": "00000",
    "msg": "success",
    "data": [
      {
        "symbol": "RIVERUSDT",
        "baseCoin": "RIVER",
        "quoteCoin": "USDT",
        "fundingRate": "0.0001"
      }
    ]
  }
  ```

#### 核心V2端点列表
| 功能 | 现货端点 | 合约端点 |
|------|----------|----------|
| 订单簿 | `/api/v2/spot/market/orderbook` | `/api/v2/mix/market/orderbook` |
| 账户余额 | `/api/v2/spot/account/assets` | `/api/v2/mix/account/accounts` |
| 下单 | `/api/v2/spot/order` | `/api/v2/mix/order/place-order` |
| 查询订单 | `/api/v2/spot/order` | `/api/v2/mix/order/detail` |
| 取消订单 | `/api/v2/spot/order` | `/api/v2/mix/order/cancel-order` |
| 持仓查询 | - | `/api/v2/mix/position/all-position` |
| 充值地址 | `/api/v2/spot/deposit/address` | - |
| 提现 | `/api/v2/spot/withdrawal/submit` | - |

#### WebSocket连接
```python
# V2 WebSocket (推荐使用)
wss://ws.bitget.com/v2/ws/public

# 订阅格式
{
  "op": "subscribe",
  "args": [{
    "instType": "SPOT",  # 或 "USDT-FUTURES"
    "channel": "books",   # ticker, trade
    "instId": "BTCUSDT"
  }]
}
```

---

### 5. Bybit

#### 现货交易对查询
```http
GET https://api.bybit.com/v5/market/tickers?category=spot
```
- **响应结构**:
  ```json
  {
    "retCode": 0,
    "result": {
      "list": [
        {
          "symbol": "RIVERUSDT",
          "baseCoin": "RIVER",
          "quoteCoin": "USDT"
        }
      ]
    }
  }
  ```

#### 合约交易对查询
```http
GET https://api.bybit.com/v5/market/tickers?category=linear
```
- **category**: `linear` = USDT永续合约

---

## 🚨 实测避坑指南

### Gate.io
1. ✅ API直接返回list，不要用 `data.get("pairs")`
2. ✅ 合约查询不需要过滤 `contract_type`
3. ✅ Symbol格式使用下划线: `RIVER_USDT`

### Bitget
1. ❌ **不要使用V1 API** (已废弃，2025年11月28日停用)
2. ❌ **没有V4 API** (V2是当前最新稳定版)
3. ✅ 现货端点: `/api/v2/spot/public/symbols`
4. ✅ 合约参数: `productType=USDT-FUTURES`
5. ✅ WebSocket: `wss://ws.bitget.com/v2/ws/public`
6. ✅ 清理代码中的所有V1 fallback逻辑

### 通用
- **符号格式转换**:
  | Binance/Bybit/Bitget | OKX | Gate.io |
  |---------------------|-----|---------|
  | `RIVERUSDT` | `RIVER-USDT` | `RIVER_USDT` |

- **响应类型判断**:
  ```python
  # Binance/Bybit/OKX: dict
  if isinstance(data, dict):
      symbols = data.get("symbols") or data.get("data") or data.get("result", {}).get("list")

  # Gate.io: 直接是list
  elif isinstance(data, list):
      symbols = data
  ```

---

## 🔧 速率限制 (Rate Limit)

| 交易所 | 限制类型 | 权重计算 |
|--------|----------|----------|
| Binance | Request Weight | 每个端点不同，详见文档 |
| OKX | API Token | 20次/2秒 (公共端点) |
| Gate.io | Request Limit | 10次/秒 (IP) |
| Bitget | IP Limit | 20次/秒 (公共) |
| Bybit | API Key | 100次/秒 (公共) |

---

## 📦 SDK 推荐

| 交易所 | Python SDK | GitHub |
|--------|-----------|--------|
| Binance | `python-binance` | https://github.com/sammchardy/python-binance |
| OKX | `okx` | https://github.com/okx-okx-okx-okx |
| Bybit | `pybit` | https://github.com/bybit-exchange/pybit |
| Gate.io | `gate-api` | https://github.com/gateio/gateapi-python |
| Bitget | `bitget-python-sdk` | https://github.com/BitgetLimited/v3-bitget-python-sdk |

---

## 📝 使用示例

```python
import requests

def check_exchange_support(exchange: str, symbol: str, market_type: str) -> bool:
    """
    检查交易对是否支持

    Args:
        exchange: binance/okx/gateio/bitget/bybit
        symbol: RIVERUSDT (统一格式)
        market_type: spot/future

    Returns:
        bool: 是否支持
    """
    # 转换符号格式
    if exchange == "okx":
        check_symbol = symbol.replace("USDT", "-USDT")
        if market_type == "future":
            check_symbol += "-SWAP"
    elif exchange == "gateio":
        check_symbol = symbol.replace("USDT", "_USDT")
    else:
        check_symbol = symbol

    # 根据交易所调用不同端点
    endpoints = {
        "binance": {
            "spot": "https://api.binance.com/api/v3/exchangeInfo",
            "future": "https://fapi.binance.com/fapi/v1/exchangeInfo"
        },
        # ... 其他交易所
    }

    # 发送请求并解析响应
    # 注意Gate.io返回list，其他返回dict
    ...
```

---

## 🔥 永续合约 DEX (Perp DEX)

> **特点**: 链上交易，需 EIP-712 签名，性能接近 CEX

### Hyperliquid 🔥 当前最火
- **文档**: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
- **特点**: 性能极高，类 CEX 体验，有 Python/Rust SDK
- **链**: Arbitrum
- **适用**: 高频交易、套利
- **推荐度**: ⭐⭐⭐⭐⭐

### dYdX (Chain/V4)
- **文档**: https://docs.dydx.exchange/
- **特点**: 迁移到 Cosmos 生态，文档详尽
- **链**: Cosmos (dYdX Chain)
- **适用**: 高性能交易
- **推荐度**: ⭐⭐⭐⭐⭐

### GMX (Arbitrum/Avalanche 龙头)
- **文档**: https://docs.gmx.io/
- **特点**: V2 引入低延迟预言机，适合流动性提供者和套利
- **链**: Arbitrum, Avalanche
- **适用**: 流动性挖矿、套利
- **推荐度**: ⭐⭐⭐⭐

### Drift Protocol (Solana 衍生品龙头)
- **文档**: https://docs.drift.trade/
- **特点**: 基于 Solana，速度极快，支持全仓保证金
- **链**: Solana
- **适用**: 高频交易
- **推荐度**: ⭐⭐⭐⭐

---

## 📊 期权与衍生品平台 (Options & Derivatives)

> **特点**: 对 API 精度和希腊字母（Greeks）计算有高要求

### Deribit (期权市场绝对龙头 - CEX)
- **文档**: https://docs.deribit.com/
- **特点**: 期权 API 行业标准
- **产品**: 永续合约、期权、期货
- **推荐度**: ⭐⭐⭐⭐⭐

### Aevo (前 Ribbon Finance - DEX)
- **文档**: https://api-docs.aevo.xyz/
- **特点**: 专注期权和永续合约，Layer 2 架构，API 风格接近 CEX
- **链**: Ethereum (Layer 2)
- **适用**: 期权交易
- **推荐度**: ⭐⭐⭐⭐

### Derive (原 Lyra Finance)
- **文档**: https://docs.derive.xyz/
- **特点**: 专注链上期权，提供波动率和价格数据
- **链**: Optimism
- **适用**: 期权策略
- **推荐度**: ⭐⭐⭐

---

## 🔮 预测市场 (Prediction Markets)

### Polymarket
- **HTTP API**: https://docs.polymarket.com/
- **WebSocket**: wss://clob.polymarket.com/ws/
- **特点**:
  - 基于 Polygon 和 CTF (合约交易框架)
  - API 支持获取市场赔率、下单、监听事件结果
- **Python SDK**: https://github.com/Polymarket/python-polymarket-sdk
- **适用**: 预测市场套利、数据收集
- **推荐度**: ⭐⭐⭐⭐⭐

---

## 💱 现货 DEX & 聚合器 (Spot DEX & Aggregator)

> **特点**: 聚合器 API 比单一交易所更重要，用于寻找最优价格

### Uniswap (以太坊/多链龙头)
- **文档**: https://docs.uniswap.org/api/overview
- **链**: Ethereum, Polygon, Arbitrum, Optimism 等
- **适用**: 现货交易、流动性提供
- **推荐度**: ⭐⭐⭐⭐⭐

### Jupiter (Solana 聚合器龙头) 🔥 强烈推荐
- **Swap API**: https://station.jup.ag/docs/apis/swap-api
- **特点**:
  - Solana 上几乎所有现货交易都经过它
  - API 简洁高效
- **链**: Solana
- **适用**: Solana 现货套利、最优路径查找
- **推荐度**: ⭐⭐⭐⭐⭐

### 1inch (多链聚合器)
- **文档**: https://docs.1inch.dev/docs
- **特点**: 适合寻找多链最优价格
- **链**: Ethereum, BSC, Polygon, Arbitrum 等
- **适用**: 跨 DEX 最优路径
- **推荐度**: ⭐⭐⭐⭐

---

## 📡 链上数据与价格喂价 (On-Chain Data)

### Pyth Network (低延迟金融数据预言机)
- **文档**: https://docs.pyth.network/
- **特点**: 低延迟价格数据，覆盖多链
- **适用**: 实时价格喂价、套利
- **推荐度**: ⭐⭐⭐⭐⭐

### CoinGecko API (全市场数据)
- **文档**: https://www.coingecko.com/en/api/documentation
- **特点**: 全市场排名和基础数据
- **适用**: 市值分析、价格监控
- **推荐度**: ⭐⭐⭐⭐

### DexScreener API (实时价格监控)
- **文档**: https://docs.dexscreener.com/api/reference
- **特点**: 监控新币/土狗实时价格
- **适用**: 链上新币发现、价格监控
- **推荐度**: ⭐⭐⭐⭐

---

## 🔄 CEX vs DEX 对比

| 维度 | CEX | DEX |
|------|-----|-----|
| **性能** | 极高 (内存撮合) | 较低 (链上确认) |
| **签名** | HMAC-SHA256 | EIP-712 / Wallet Signature |
| **延迟** | 毫秒级 | 秒级 (受区块时间影响) |
| **费用** | 手续费低 | Gas 费高 |
| **KYC** | 需要 | 无需 |
| **托管** | 中心化 | 自托管 |
| **流动性** | 深度好 | 依赖 LP |

---

## 🔄 更新日志

- **2026-01-19 v1.2**: ⚡ 更新Bitget API版本信息
  - 明确Bitget V2是当前最新稳定版本
  - 添加V4 API不存在的说明
  - 补充Bitget核心V2端点列表
  - 新增WebSocket连接示例
- **2026-01-19 v1.1**: 新增 DEX、衍生品、预测市场 API
- **2026-01-19 v1.0**: 初始版本，基于 RIVER/USDT 交易对实测验证
- ✅ 验证 Bitget V2 端点正确性
- ✅ 修正 Gate.io 响应格式理解
- ✅ 记录所有交易所符号格式差异

---

## 💡 使用建议

### 选择交易所优先级

1. **现货套利**:
   - 优先: Binance, OKX, Bybit (CEX)
   - 辅助: Jupiter (Solana), 1inch (多链)

2. **永续合约套利**:
   - 优先: Hyperliquid, dYdX (DEX)
   - 辅助: Binance, OKX (CEX)

3. **期权策略**:
   - 首选: Deribit (流动性最好)
   - 备选: Aevo, Derive

4. **预测市场**:
   - 首选: Polymarket

### 开发注意事项

1. **DEX 签名**:
   ```python
   # EIP-712 签名示例 (Hyperliquid)
   from eth_account import Account
   import json

   message = {
       "type": "order",
       "symbol": "BTC",
       "side": "buy",
       # ... 其他字段
   }

   signed_msg = Account.sign_message(
       json.dumps(message).encode(),
       private_key
   )
   ```

2. **WebSocket 推荐**:
   - CEX: Binance, OKX (稳定性好)
   - DEX: Hyperliquid, Polymarket (延迟低)

3. **SDK 优先**:
   - DEX 开发优先使用官方 SDK
   - 避免手动处理签名和序列化

---

**技能使用提示**:
当遇到任何交易所API调用问题时，先查阅此文档。如果发现API变更或有新的注意事项，请及时更新此文档。
