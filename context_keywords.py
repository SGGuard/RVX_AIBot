import re

# ============================================================================
# КРИПТО И БЛОКЧЕЙН АКТИВЫ
# ============================================================================
crypto_words = [
    # Основные криптовалюты
    "bitcoin", "btc", "ethereum", "eth", "binance", "bnb", "solana", "sol", "cardano", "ada",
    "ripple", "xrp", "polkadot", "dot", "litecoin", "ltc", "dogecoin", "doge", "monero", "xmr",
    "tron", "trx", "ton", "avax", "avalanche", "ftm", "fantom", "cosmos", "atom", "near",
    
    # Топ альткойны и DeFi проекты
    "uniswap", "uni", "aave", "lend", "compound", "sushiswap", "curve", "yearn", "makerdao", "dai",
    "chainlink", "link", "polygon", "matic", "arbitrum", "arb", "optimism", "op",
    "lido", "ldo", "rocket", "rpl", "frax", "frxeth", "stakewise", "swise",
    
    # Биржи и торговля
    "spot", "futures", "margin", "leverage", "perpetual", "перпы", "контракты", "спот",
    "trading", "торговля", "trading pair", "торговая пара", "pair", "пара",
    "coinbase", "kraken", "okx", "bybit", "kucoin", "huobi", "gateio", "crypto.com",
    "gemini", "upbit", "bithumb", "coincheck", "bitstamp",
    
    # События с монетами
    "listing", "листинг", "delisting", "делистинг", "withdrawal", "вывод",
    "deposit", "пополнение", "halving", "халвинг", "fork", "форк",
    "airdrop", "эирдроп", "launchpad", "ico", "ido", "launch", "запуск", "release", "выпуск",
    
    # Технология
    "blockchain", "блокчейн", "smart contract", "смарт контракт",
    "protocol", "протокол", "layer 2", "l2", "lightning", "mainnet", "testnet",
    "sidechain", "rollup", "zk", "zero knowledge", "plasma",
    
    # Активности
    "staking", "стейкинг", "yield farming", "фарминг", "liquidity pool", "пул ликвидности",
    "mining", "майнинг", "validator", "валидатор", "node", "нода",
    
    # Базовые термины
    "wallet", "кошелек", "exchange", "биржа", "token", "токен", "coin", "монета",
    "altcoin", "альткоин", "defi", "дефай", "nft", "nfts", "web3", "веб3",
    "liquidity", "ликвидность", "volume", "объем", "tvl", "aum", "mcap", "market cap",
    "usdt", "usdc", "dai", "stablecoin",
]

# ============================================================================
# ТРАДИЦИОННЫЕ ФИНАНСЫ И МАКРОЭКОНОМИКА
# ============================================================================
finance_words = [
    # Центральные банки и органы регулирования
    "fomc", "фрс", "федеральный резерв", "federal reserve", "fed",
    "ecb", "европейский центральный банк", "центробанк", "центральный банк",
    "boe", "bank of england", "банк англии",
    "boj", "bank of japan", "банк японии", "боджя",
    "pboc", "народный банк китая", "pboc", "снб", "cbr", "cbrf",
    "imf", "мвф", "international monetary fund",
    "world bank", "всемирный банк",
    "bis", "банк международных расчетов",
    
    # Процентные ставки
    "ставка", "ставки", "rate", "interest rate", "процентная ставка",
    "fed rate", "fed funds rate", "ставка фед",
    "benchmark rate", "базовая ставка", "key rate", "ключевая ставка",
    "повышение ставки", "снижение ставки", "повышение", "снижение",
    "raise", "cut", "hike", "increase", "decrease", "изменение ставки",
    "basis points", "bp", "базисные пункты", "б.п.",
    
    # Инфляция и цены
    "инфляция", "inflation", "deflationary", "дефляция",
    "cpi", "потребительский индекс цен", "consumer price index",
    "pce", "личные расходы на потребление",
    "ppi", "producer price index", "индекс цен производителя",
    "core inflation", "базовая инфляция",
    "price", "цена", "prices", "цены",
    "rising prices", "растущие цены", "growing prices",
    
    # Рынки акций и индексы
    "s&p 500", "sp500", "sp 500", "s&p",
    "dow jones", "dow", "djia",
    "nasdaq", "nasdaq-100", "nasdaq 100",
    "russell 2000", "russell",
    "股票", "акции", "stocks", "shares", "equities",
    "stock market", "фондовый рынок", "рынок акций",
    "bullish", "бычий", "bullish market", "бычий рынок",
    "bearish", "медвежий", "bearish market", "медвежий рынок",
    "rally", "ралли", "selloff", "распродажа", "crash", "обвал",
    "correction", "коррекция", "rebound", "отскок",
    
    # Облигации и долг
    "bonds", "облигации", "treasuries", "казначейства",
    "treasury bonds", "казначейские облигации",
    "t-bonds", "t-bills", "t-notes",
    "10-year", "10-летние", "10y",
    "yield", "доходность", "bond yield", "доходность облигаций",
    "credit spread", "кредитный спред",
    "duration", "дюрация",
    "government bonds", "государственные облигации",
    "corporate bonds", "корпоративные облигации",
    "cds", "credit default swap", "своп дефолта", "страховка дефолта",
    "debt", "долг", "долги",
    
    # Крупные компании (Tech, Finance, Energy)
    "apple", "aapl", "appl",
    "microsoft", "msft",
    "google", "alphabet", "googl",
    "amazon", "amzn",
    "meta", "facebook", "fb",
    "nvidia", "nvda",
    "tesla", "tsla",
    "oracle", "orcl",
    "ibm",
    "cisco", "csco",
    "intel", "intc",
    "amazon web services", "aws",
    "samsung", "sony",
    "toyota", "gm",
    "jpmorgan", "morgan stanley", "goldman sachs", "gs",
    "bank of america", "bofa", "bac",
    "citigroup", "c",
    "wells fargo", "wf",
    
    # Финансовые показатели и события
    "earnings", "доходы", "earnings report", "отчет о доходах",
    "guidance", "прогноз", "forecast",
    "earnings call", "конференция по доходам",
    "quarterly", "квартальный",
    "pre-market", "до открытия", "after-hours",
    "ipo", "ipo", "initial public offering", "первичное размещение",
    "merger", "слияние", "acquisition", "приобретение",
    "spinoff", "выделение",
    "gbp", "британский фунт", "sterling",
    "jpy", "японская йена", "yen",
    "cny", "китайский юань", "yuan", "yuan renminbi",
    "rub", "российский рубль", "рубль",
    "forex", "валютный рынок", "foreign exchange",
    "currency pair", "валютная пара", "валютные пары",
    "eurusd", "gbpusd", "usdjpy", "usdcny",
    
    # Товары и сырьё
    "gold", "золото", "silver", "серебро",
    "oil", "нефть", "crude oil", "сырая нефть",
    "gas", "природный газ", "natural gas",
    "copper", "медь", "zinc", "цинк", "aluminum", "алюминий",
    "commodities", "сырьевые товары", "товары",
    "energy", "энергия", "энергетика",
    "precious metals", "драгоценные металлы",
    
    # Экономические показатели
    "gdp", "валовой внутренний продукт", "gross domestic product",
    "employment", "занятость", "unemployment", "безработица",
    "jobs report", "отчет о рабочих местах", "payroll",
    "nfp", "non-farm payroll",
    "consumer confidence", "доверие потребителей",
    "manufacturing", "производство", "manufacturing pmi",
    "retail sales", "розничные продажи", "retail",
    "housing starts", "начало строительства",
    "ifo", "zew", "pmi", "sentiment",
    
    # Волатильность и риск
    "volatility", "волатильность", "vix", "volatility index",
    "震盪", "震荡", "турбулентность",
    "correction", "коррекция",
    "risk", "риск", "risks",
    "uncertainty", "неопределённость",
    "geopolitical", "геополитический",
    
    # Монетарная политика
    "quantitative easing", "количественное смягчение", "qe",
    "quantitative tightening", "количественное ужесточение", "qt",
    "tapering", "завершение программы",
    "stimulus", "стимул", "stimulative",
    "accommodative", "мягкая политика",
    "hawkish", "ястребиная политика", "hawk", "ястреб",
    "dovish", "голубиная политика", "dove", "голубь",
    
    # Финансовые события и отчеты
    "earnings", "доходы", "earnings report", "отчет о доходах",
    "guidance", "прогноз", "forecast",
    "earnings call", "конференция по доходам",
    "quarterly", "квартальный",
    "pre-market", "до открытия", "after-hours",
    "ipo", "ipo", "initial public offering", "первичное размещение",
    "merger", "слияние", "acquisition", "приобретение",
    "spinoff", "выделение",
]

# ============================================================================
# ДЕЙСТВИЯ И СОБЫТИЯ (глаголы, процессы)
# ============================================================================
action_words = [
    # Удаление и закрытие - критичное
    "удален", "удаление", "удалит", "удаляет", "удалены", "удаляем",
    "delist", "delisted", "delisting", "удалять из листинга",
    "закрыт", "закрытие", "закрыла", "закроет", "закрывается", "закроем",
    "прекращено", "прекращение", "прекращает", "остановлен", "остановка",
    "suspended", "приостановлен", "приостановка", "заморожен", "frozen",
    "disable", "отключен", "отключение", "списан", "списание",
    "removed from", "exclude", "excluded", "terminate", "terminated",
    
    # Запуск и добавление
    "запуск", "запустил", "запустили", "запускает", "запустим",
    "launch", "launched", "launching", "add", "added", "добавлен", "добавление",
    "release", "released", "выпуск", "выпустили", "выпущен",
    "listing", "listed", "added to", "integration", "интеграция", "integrated",
    "support", "поддержка", "supported", "поддерживает", "поддерживаем",
    "mint", "minting", "монетизация", "burn", "burning",
    
    # Партнёрства и сотрудничество
    "партнерство", "partnership", "партнёр", "партнеры",
    "сотрудничество", "collaboration", "cooperate", "cooperation",
    "announce", "announced", "announcement", "объявляет", "объявили", "объявление",
    "merge", "merged", "слияние", "acquisition", "приобретение", "acquired",
    "join", "joined", "присоединяется", "integrate", "partnership agreement",
    
    # Взломы и проблемы безопасности
    "hack", "хакнули", "взлом", "взломан", "exploit", "exploited", "eploitation",
    "breach", "breached", "vulnerability", "уязвимость",
    "security", "безопасность", "issue", "проблема", "bug", "баг", "bugs",
    "attack", "атака", "compromised", "компрометирован", "compromised",
    "malicious", "вредоносный", "threat", "угроза",
    
    # Обновления и улучшения
    "upgrade", "обновление", "обновлен", "обновляется", "update", "updated",
    "improvement", "улучшение", "enhancement", "оптимизация", "optimized",
    "fix", "исправление", "fixed", "patch", "patched",
    "feature", "функция", "feature release", "версия", "version",
    "beta", "preview", "prod", "production", "deployment", "deployed",
    
    # Финансовые события
    "funding", "привлечение", "инвестиции", "investment", "raise", "серия",
    "seed", "series a", "series b", "series c", "series d",
    "ipo", "токен сейл", "token sale", "presale",
    "buyback", "выкуп", "burn", "сжигание", "redistribute", "перераспределение",
    "revenue", "выручка", "profit", "прибыль", "loss", "убыток",
    
    # Технические события
    "fork", "форк", "mainnet", "testnet", "migration", "миграция", "migrate",
    "consensus", "консенсус", "difficulty adjustment", "halving", "халвинг",
    "hard fork", "soft fork", "upgrade", "deployment", "deploy",
    
    # Регуляция и соответствие
    "regulatory", "регуляция", "compliance", "соответствие", "comply",
    "approved", "одобрена", "одобрено", "approve", "approval",
    "rejected", "отклонена", "reject", "ban", "запрет", "banned",
    "sanction", "санкция", "санкции", "lawsuit", "судебный процесс",
    "investigation", "расследование", "sec", "sec approval",
    
    # Персонал и организационные изменения
    "hiring", "нанимает", "hiring now", "hiring open", "нанять",
    "recruitment", "recruiter", "набор", "набирать", "recruit",
    "join", "join us", "join our team", "присоединиться", "welcome",
    "team", "команда", "staff", "сотрудники", "employees", "работники",
    "ceo", "founder", "team lead", "manager", "executive",
    
    # Рыночные действия
    "surge", "скачок", "скачок вверх", "jump", "прыжок",
    "plunge", "падение", "collapse", "обрушение", "crash", "крах",
    "rally", "ралли", "подъем", "rebound", "отскок", "bounce",
    "decline", "снижение", "drop", "спад", "fall",
    "rise", "рост", "increase", "увеличение",
    "reverse", "разворот", "retreat", "откат",
    
    # Разное
    "breaking", "срочно", "critical", "критичное", "important", "важное",
    "urgent", "срочное", "news", "новость", "update", "обновление",
    "notice", "уведомление", "alert", "предупреждение", "notification",
]

# ============================================================================
# ТЕХНОЛОГИИ И КОМПАНИИ (AI, веб3, стартапы, разработка)
# ============================================================================
tech_keywords = [
    # AI и LLM модели
    "ai", "искусственный интеллект", "artificial intelligence",
    "chatgpt", "gpt-3", "gpt-4", "gpt-4o", "gpt-4-turbo", "gpt-5",
    "claude", "claude 3", "claude 3 opus", "claude 3 sonnet",
    "deepseek", "deepseek v2", "deepseek r1", "deepseek-coder", "deepseek-vl",
    "gemini", "gemini pro", "gemini ultra", "bard", "palm", "palm-2",
    "llama", "llama 2", "llama 3", "mistral", "mistral large", "mixtral",
    "openai", "anthropic", "google", "meta", "microsoft",
    
    # ML и технологии
    "machine learning", "ml", "deep learning", "dl", "neural network", "нейросеть",
    "transformer", "attention mechanism", "rlhf", "fine-tuning", "inference",
    "embedding", "vector", "rag", "retrieval-augmented generation",
    "model", "model release", "model update", "модель", "модели",
    
    # Blockchain и Web3 разработка
    "blockchain", "smart contract", "solidity", "vyper", "rust", "move",
    "dapp", "decentralized app", "dao", "децентрализованная автономная организация",
    "web3", "веб3", "metaverse", "nft", "defi", "yield", "layer 2",
    "evm", "ethereum virtual machine", "chain", "сеть",
    
    # Платформы и инструменты разработки
    "github", "gitlab", "docker", "kubernetes", "cloud",
    "aws", "gcp", "azure", "ci/cd", "devops",
    "api", "sdk", "library", "framework", "library",
    
    # Компании Web3 и Блокчейн
    "nethermind", "consensys", "etherscan", "blocknative",
    "alchemy", "infura", "quicknode", "llamapay", "tenderly",
    "uniswap labs", "aave labs", "yearn", "curve labs",
    "metamask", "ledger", "trezor", "gnosis safe",
    "web3 foundation", "ethereum foundation", "ethereum development",
    
    # Должности и специальности - Крипто/Web3
    "blockchain engineer", "smart contract engineer", "solidity developer",
    "rust developer", "web3 developer", "dapp developer", "backend engineer",
    "frontend developer", "fullstack engineer", "devops engineer",
    "protocol engineer", "security researcher", "auditor",
    "senior", "senior developer", "senior engineer", "lead", "principal",
    
    # Должности и специальности - Общее
    "developer", "engineer", "architect", "manager", "director",
    "technical lead", "team lead", "product manager", "project manager",
    "executive", "cto", "ceo", "founder", "co-founder",
    "data scientist", "ml engineer", "ai researcher",
    
    # Вакансии и найм
    "hiring", "hiring now", "hiring open", "нанимает", "hiring position",
    "recruitment", "recruiter", "вакансия", "вакансии", "работа", "работы",
    "должность", "должности", "position", "positions", "opening",
    "employment", "hire", "hiring", "job", "jobs", "opportunity",
    "join", "join us", "join our team", "join the team", "become part",
    "work", "career", "карьера", "возможность", "opportunity",
    "apply", "apply now", "application", "candidate", "interview",
    
    # Конференции и события
    "conference", "summit", "event", "конференция", "встреча",
    "devcon", "ethereum", "ethtokyo", "ethcc", "eth denver",
    "web3", "web3 summit", "ai conference", "ai summit",
    "announcement", "keynote", "presentation", "talk",
    
    # Обновления и релизы
    "launch", "launch new", "new model", "new feature", "new product",
    "api", "release", "beta", "beta release", "launch api", "sdk",
    "integration", "integrate", "support", "support for",
    "update", "версия", "version", "v1", "v2", "v3",
    
    # Технологии и протоколы
    "ethereum", "ethereum upgrade", "eth2", "ethereum 2.0",
    "proof of stake", "pos", "proof of work", "pow",
    "sharding", "rollups", "optimistic rollup", "zk rollup",
    "consensus", "layer 1", "layer 2", "sidechain",
]

# ============================================================================
# NEWS PATTERNS - РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ДЛЯ СЛОЖНЫХ ПАТТЕРНОВ
# ============================================================================
news_patterns = [
    # ========================================================================
    # ФЕДЕРАЛЬНАЯ РЕЗЕРВНАЯ СИСТЕМА (ФРС) И ПРОЦЕНТНЫЕ СТАВКИ
    # ========================================================================
    re.compile(r"\b(fomc|фрс|federal reserve|fed|федеральный резерв)\b.*\b(meeting|заседание|decision|решение|rate|ставка)\b", re.IGNORECASE),
    re.compile(r"\b(rate|ставка)\b.*(cut|hike|снижение|повышение|increase|decrease|raise)\b", re.IGNORECASE),
    re.compile(r"\b(fed|фрс)\b.*\b(cut|hike|снижение|повышение)\b.*\%|\d+\s*(bp|б\.п\.)", re.IGNORECASE),
    re.compile(r"(процентная ставка|interest rate|fed rate).*\b(снижение|повышение|cut|hike|rise|fall)\b", re.IGNORECASE),
    
    # ========================================================================
    # ВОЛАТИЛЬНОСТЬ И РЫНОЧНЫЕ СОБЫТИЯ
    # ========================================================================
    re.compile(r"\b(volatility|волатильность|vix|震荡|震盪)\b.*\b(increase|decrease|spike|surge|подъем|падение|снижение)\b", re.IGNORECASE),
    re.compile(r"\b(market|рынок)\b.*(volatility|волатильность|turbulent|турбулентный|uncertain|неопределённый)", re.IGNORECASE),
    
    # ========================================================================
    # РЫНКИ АКЦИЙ И ИНДЕКСЫ
    # ========================================================================
    re.compile(r"\b(s&p|sp500|dow jones|nasdaq|dow|djia|акции|stocks)\b", re.IGNORECASE),
    re.compile(r"\b(stock market|фондовый рынок|shares|акции)\b.*\b(surge|rally|crash|fall|rise|скачок|падение|рост)\b", re.IGNORECASE),
    re.compile(r"\b(bullish|bearish|correction|rally|selloff|ралли|распродажа|коррекция)\b", re.IGNORECASE),
    
    # ========================================================================
    # ОБЛИГАЦИИ И ДОХОДНОСТЬ
    # ========================================================================
    re.compile(r"\b(bonds?|облигация|treasury|treasuries|казначейство|yield|доходность)\b", re.IGNORECASE),
    re.compile(r"\b(10-year|10y|10-летние)\b", re.IGNORECASE),
    re.compile(r"\b(bond yield|treasury yield|доходность облигаций)\b", re.IGNORECASE),
    
    # ========================================================================
    # ВАЛЮТНЫЕ ПАРЫ И FOREX
    # ========================================================================
    re.compile(r"\b(eurusd|gbpusd|usdjpy|usdcny|forex|валютный рынок)\b", re.IGNORECASE),
    re.compile(r"\b(currency|валюта|dollar|доллар|euro|евро)\b.*\b(strength|weakness|слабость|укрепление)\b", re.IGNORECASE),
    re.compile(r"\b(usd|eurusd|gbp|jpy|cny)\b.*\b(surge|fall|gain|lose|рост|падение)\b", re.IGNORECASE),
    
    # ========================================================================
    # ИНФЛЯЦИЯ И ЦЕНЫ
    # ========================================================================
    re.compile(r"\b(inflation|инфляция|cpi|ppi|price|цена|prices|цены)\b", re.IGNORECASE),
    re.compile(r"\b(rising prices|растущие цены|inflation data|данные инфляции|core inflation|базовая инфляция)\b", re.IGNORECASE),
    re.compile(r"\b(inflationary|инфляционный|deflationary|дефляция)\b", re.IGNORECASE),
    
    # ========================================================================
    # ЭКОНОМИЧЕСКИЕ ДАННЫЕ И ПОКАЗАТЕЛИ
    # ========================================================================
    re.compile(r"\b(gdp|unemployment|employment|jobs|nfp|payroll|розничные продажи)\b", re.IGNORECASE),
    re.compile(r"\b(economic data|экономические данные|jobs report|employment report|отчет о рабочих местах)\b", re.IGNORECASE),
    re.compile(r"\b(manufacturing|pmi|consumer confidence|retail sales|housing)\b", re.IGNORECASE),
    
    # ========================================================================
    # КРИТИЧНЫЕ: Делистинг и закрытие торговых пар
    # ========================================================================
    re.compile(r"(binance|coinbase|kraken|okx|bybit|huobi|gate\.io).*\b(delist|remove|удалит|удален|закроет|закроет|спишет|делист)\b.*(pair|token|coin|пару|токен|монету|торговой пары)", re.IGNORECASE),
    re.compile(r"\b(delist|remove|exclude|terminate|закроет|удалит|спишет|делист|исключит|удаляет)\b.*(token|coin|pair|trading pair|пару|монету|торговой|котировку)", re.IGNORECASE),
    
    # ========================================================================
    # ВАЖНЫЕ: Запуск новых продуктов и функций
    # ========================================================================
    re.compile(r"\b(запуск|launch|release|выпуск|debut|announce|объявляет)\b.*(новой|новую|new|product|feature|продукта|функции|возможности)", re.IGNORECASE),
    
    # ========================================================================
    # ВАКАНСИИ И НАЙМ
    # ========================================================================
    re.compile(r"(nethermind|consensys|alchemy|infura|metamask|tenderly).*\b(hiring|recruiting|recruitment|нанимает|ищет вакансию|work with|join)\b", re.IGNORECASE),
    re.compile(r"\b(blockchain engineer|smart contract engineer|solidity developer|rust developer|web3 developer)\b", re.IGNORECASE),
    
    # ========================================================================
    # ГЕОПОЛИТИКА И МЕЖДУНАРОДНЫЕ ОТНОШЕНИЯ
    # ========================================================================
    re.compile(r"\b(russia|ukraine|china|usa|united states|eu|nato|israel|iran|north korea|south korea|taiwan)\b.*\b(war|conflict|invasion|military|sanctions|tension|crisis)\b", re.IGNORECASE),
    re.compile(r"\b(russian|ukrainian|chinese|american|israeli|iranian)\b.*\b(military|army|forces|troops|attack|strike|invasion|war)\b", re.IGNORECASE),
    re.compile(r"\b(war|война|conflict|конфликт|invasion|вторжение|military operation|операция)\b.*\b(russia|ukraine|china|middle east|asia|europe)\b", re.IGNORECASE),
    re.compile(r"\b(sanctions|санкции|embargo|эмбарго|blockade|блокада)\b.*\b(russia|china|iran|north korea|countries|страны)\b", re.IGNORECASE),
    re.compile(r"\b(nato|нато)\b.*\b(expansion|расширение|member|членство|ukraine|finland|sweden|latvija|estonia|lithuania)\b", re.IGNORECASE),
    re.compile(r"\b(peace|peace talks|peace agreement|договор|agreement|ceasefire|перемирие|negotiations|переговоры)\b.*\b(russia|ukraine|middle east|israel|palestine|hamas)\b", re.IGNORECASE),
    re.compile(r"\b(election|election results|vote|voting|выборы|референдум|referendum)\b.*\b(russia|china|usa|europe|country|страна)\b", re.IGNORECASE),
    re.compile(r"\b(tariffs|тарифы|trade war|торговая война|trade sanctions|торговые санкции)\b", re.IGNORECASE),
    re.compile(r"\b(geopolitical|геополитический|international crisis|международный кризис|diplomatic|дипломатический)\b", re.IGNORECASE),
]

# ============================================================================
# ГЕОПОЛИТИКА И МЕЖДУНАРОДНЫЕ СОБЫТИЯ
# ============================================================================
geopolitical_words = [
    # Страны и региональные блоки
    "russia", "рф", "российской", "россия", "русский",
    "ukraine", "украины", "украина", "украинский",
    "china", "китай", "китайский", "chinese",
    "usa", "united states", "america", "american", "сша", "американский",
    "eu", "european union", "европейский союз", "european", "европа",
    "nato", "нато",
    "india", "индия", "индийский",
    "japan", "япония", "japanese", "японский",
    "south korea", "korea", "корея", "корейский", "south korean",
    "north korea", "north korean", "северная корея", "кндр",
    "taiwan", "тайвань", "taiwanese",
    "israel", "израиль", "израильский", "israeli",
    "palestine", "палестина", "palestinians",
    "iran", "иран", "иранский",
    "iraq", "иран", "иракский",
    "syria", "сирия", "сирийский",
    "middle east", "ближний восток", "middle eastern",
    "gulf", "персидский залив",
    "germany", "германия", "немецкий", "german",
    "france", "франция", "французский", "french",
    "uk", "united kingdom", "britain", "british", "великобритания", "британский",
    "italy", "italy", "итальянский", "italian",
    "spain", "испания", "испанский",
    "poland", "польша", "польский",
    "hungary", "венгрия", "венгерский",
    "czech", "чехия", "чешский",
    "turkey", "турция", "турецкий", "turkish",
    "russia", "рф",
    
    # Конфликты и военные операции
    "war", "война", "wars", "войны",
    "conflict", "конфликт", "conflicts", "конфликты",
    "invasion", "вторжение", "invasions",
    "military", "военный", "military operation", "военная операция",
    "army", "армия", "armies", "армий",
    "forces", "войска", "силы", "troops", "боевые",
    "soldier", "солдат", "soldiers", "боец", "бойцы",
    "general", "генерал", "генеральный",
    "commander", "командующий", "commander-in-chief",
    "attack", "атака", "атаке", "attacked", "attacks", "нападение",
    "strike", "удар", "удары", "strikes", "нанести удар",
    "bombing", "бомбежка", "bombing campaign", "bombardment", "бомбардировка",
    "shoot", "стрелять", "shooting", "gunfire", "огонь", "пулемет",
    "combat", "боевые", "battle", "битва", "боевых",
    "tank", "танки", "tanks", "танка",
    "missile", "ракета", "ракеты", "missiles", "missile attack",
    "drone", "дрон", "дроны", "дроне", "drone strike",
    "artillery", "артиллерия", "артиллерийский",
    "weapons", "оружие", "weapons system", "оружия",
    "nuclear", "ядерный", "ядерное", "nuclear weapon", "nuclear war",
    "weapon of mass destruction", "wmd",
    
    # Санкции и экономические меры
    "sanctions", "санкции", "sanction", "санкция",
    "embargo", "эмбарго", "embargoes",
    "blockade", "блокада", "blockade",
    "restrictions", "ограничения", "restriction",
    "freeze", "заморозить", "frozen assets", "замороженные активы",
    "tariffs", "тарифы", "tariff", "таможенный тариф",
    "trade war", "торговая война",
    "export controls", "контроль экспорта",
    "import", "импорт", "imports",
    "export", "экспорт", "exports",
    
    # Дипломатические события
    "diplomacy", "дипломатия", "diplomatic", "дипломатический",
    "negotiations", "переговоры", "negotiate", "договариваться",
    "talks", "переговоры", "talks between", "talks with",
    "summit", "саммит", "summits",
    "meeting", "встреча", "встреча лидеров", "bilateral meeting",
    "agreement", "соглашение", "agreements", "accord", "аккорд",
    "treaty", "договор", "treaties",
    "ceasefire", "перемирие", "ceasefire agreement",
    "peace", "мир", "peace talks", "peace agreement", "peace process",
    "ambassador", "посол", "ambassador meeting", "ambassador talks",
    "envoy", "посланник", "envoy visit",
    "statement", "заявление", "statement from government",
    "government", "правительство",
    "ministry", "министерство",
    "foreign affairs", "иностранные дела",
    "foreign office", "внешнеполитическое ведомство",
    
    # Политические события
    "election", "выборы", "elections", "election day",
    "referendum", "референдум",
    "vote", "голос", "votes", "voting", "голосование",
    "coup", "переворот", "coup d'etat",
    "protest", "протест", "protests", "демонстрация", "demonstration",
    "riot", "бунт", "riots", "бунты",
    "uprising", "восстание", "revolution", "революция",
    "government", "правительство", "regime", "режим",
    "leader", "лидер", "leaders", "политический лидер",
    "president", "президент", "president of",
    "prime minister", "премьер-министр", "pm",
    "parliament", "парламент", "parliament member",
    "congress", "конгресс",
    "senate", "сенат", "senator",
    "minister", "министр", "minister of",
    "chancellor", "канцлер", "chancellor of",
    
    # Международные организации
    "united nations", "ООН", "un", "united nations security council", "unsc",
    "security council", "совет безопасности",
    "world bank", "всемирный банк",
    "imf", "international monetary fund", "международный валютный фонд",
    "wto", "world trade organization", "всемирная торговая организация",
    "oecd", "oecd member",
    "g7", "g-7", "group of seven", "семерка",
    "g20", "g-20", "group of twenty",
    "brics", "брикс",
    "opec", "opec+", "опек",
    
    # Территориальные и пограничные вопросы
    "border", "граница", "borders", "boundary",
    "territory", "территория", "territorial",
    "occupation", "оккупация", "occupied", "оккупированные",
    "annexation", "аннексия", "annex", "аннексировать",
    "independence", "независимость", "independent",
    "secession", "сецессия", "secede",
    "disputed", "спорный", "disputed territory", "спорная территория",
    "sea", "море", "sea of japan", "japan sea", "south china sea", "east china sea",
    "straits", "пролив", "strait of taiwan", "taiwan strait", "bering strait",
    
    # Кризисы и чрезвычайные ситуации
    "crisis", "кризис", "crises", "критическая ситуация",
    "emergency", "чрезвычайный", "emergency situation", "чрезвычайная ситуация",
    "disaster", "катастрофа", "disaster relief",
    "humanitarian", "гуманитарный", "humanitarian crisis",
    "refugee", "беженец", "refugees", "беженцы", "refugee crisis",
    "migration", "миграция", "migrants",
    "terrorism", "терроризм", "terrorist", "террорист", "terrorist attack",
    "extremism", "экстремизм",
    "insurgency", "мятеж", "insurgent", "повстанец",
    
    # Экономические и финансовые санкции
    "oligarch", "олигарх", "oligarchs",
    "asset freeze", "заморозка активов",
    "bank", "банк", "banking sector", "банковский",
    "currency", "валюта", "currency restrictions",
    "energy", "энергия", "energy sanctions", "energy supplies",
    "oil", "нефть", "oil sanctions", "oil prices",
    "gas", "газ", "natural gas", "природный газ", "gas supplies",
    
    # Территории и города (конфликтные зоны)
    "donbas", "донбасс",
    "donets", "донец",
    "crimea", "крым", "крымский",
    "moscow", "москва", "московский",
    "kyiv", "киев", "киевский",
    "beijing", "пекин", "пекинский",
    "washington", "вашингтон", "washington dc",
    "kabul", "кабул", "афганистан",
    "tehran", "тегеран", "иран",
    "damascus", "дамаск", "сирия",
    "beirut", "бейрут", "ливан",
    "gaza", "газа", "газовый сектор",
    "west bank", "западный берег",
    "hong kong", "гонконг",
    "taiwan strait", "тайванский пролив",
    "south china sea", "южно-китайское море",
    "east china sea", "восточно-китайское море",
    
    # Различные события
    "terror", "террор",
    "hostage", "заложник", "hostages", "заложники",
    "prisoner", "заключенный", "prisoners",
    "execution", "казнь", "executions",
    "human rights", "права человека",
    "war crimes", "военные преступления",
    "genocide", "геноцид",
    "ethnic cleansing", "этническая чистка",
    "asylum", "убежище", "asylum seeker",
    
    # Инфраструктура и стратегические активы
    "infrastructure", "инфраструктура",
    "power plant", "электростанция",
    "pipeline", "трубопровод",
    "rail", "железная дорога",
    "port", "порт", "ports",
    "airport", "аэропорт", "airport strike",
    "bridge", "мост", "bridge destroyed",
    "dam", "дамба", "damming",
]
