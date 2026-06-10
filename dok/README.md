# 🏥 Dòk GlorYah - Asistan Sante Entelijan

Application médicale web légère et optimisée pour Haïti, utilisant l'IA pour fournir des conseils de santé en créole haïtien.

## 📋 Ki sa Dòk GlorYah ye?

Dòk GlorYah se yon aplikasyon medikal ki itilize entèlijans atifisyèl (IA) pou ede moun jwenn enfòmasyon sou sante yo. Ou ka ekri sentòm ou yo an kreyòl oswa an fransè, epi aplikasyon an ap ba ou konsèy.

### ✨ Karakteristik

- 🤖 **IA lokal** - Pa bezwen entènèt rapid oswa API peyan
- 🇭🇹 **Kreyòl ayisyen** - Repons yo an kreyòl senp
- 📱 **Mobile-first** - Optimize pou telefòn Android
- 🟢🟡🔴 **Klasifikasyon otomatik** - Sistèm detekte gravite ka a
- 💬 **Kontak WhatsApp** - Fasil pou kontakte yon moun
- 🌙 **Mòd fènwa** - Sipò pou mòd nwa otomatik
- ⚡ **Rapid** - Optimizasyon pou entènèt ki pa rapid

## 🚀 Kijan pou instale l

### Prérequis

- Python 3.8 oswa plis wo
- pip (enstale avèk Python)

### Etap 1: Telechaje kòd la

```bash
cd dok_gloryah
```

### Etap 2: Enstale depandans yo

```bash
pip install -r requirements.txt
```

Oswa si sa pa mache:

```bash
pip install Flask==3.0.0 Werkzeug==3.0.1
```

### Etap 3: Lanse aplikasyon an

```bash
python app.py
```

Ou ap wè:
```
==================================================
🏥 Dòk GlorYah - Asistan sante entelijan
==================================================
📱 Aplikasyon ap kouri sou: http://localhost:5000
🌐 Pou mobile: http://0.0.0.0:5000
==================================================
```

### Etap 4: Ouvè nan navigatè

- **Sou òdinatè a**: Ale nan `http://localhost:5000`
- **Sou telefòn mobile**: Jwenn adrès IP lokal òdinatè a (pa egzanp `http://192.168.1.10:5000`)

## 📱 Kijan pou itilize l

1. **Ekri sentòm ou yo** nan bwat tèks la
   - Egzanp: "Mwen gen lafyèv epi tèt mwen fè mal"
   
2. **Klike sou "Mande Konsèy"**

3. **Li repons IA a** ki ap montre ou:
   - 🟢 VÈT = Pa grav
   - 🟡 JÒN = Moyen
   - 🔴 WOUJ = Ijans
   
4. **Si bezwen**, klike sou "Kontakte sou WhatsApp" pou pale ak yon moun

## 🧠 Kijan IA a fonksyone

L'IA utilise un système de règles intelligentes pour:

1. **Analize** tèks ou ekri a
2. **Detekte** mo kle ak sentòm enpòtan yo
3. **Klasifye** gravite a (lejè, moyen, ijans)
4. **Jenere** yon repons apwopriye an kreyòl

### Egzanp sentòm ijans (🔴):
- Doulè nan kè
- Pa ka respire
- Pèdi konesans
- Senyen anpil
- Konvulsion

### Egzanp sentòm moyen (🟡):
- Lafyèv
- Toux
- Doule vant
- Dyare
- Fatig

## 📁 Estrikti pwojè

```
dok_gloryah/
├── app.py              # Fichier principal Flask
├── requirements.txt    # Dépendances Python
├── README.md          # Documentation
├── templates/
│   └── index.html     # Interface web
├── static/
│   └── style.css      # Styles CSS
└── ai/
    ├── __init__.py
    └── model.py       # Moteur IA local
```

## ⚙️ Konfigirasyon

### Chanje pò (port)

```bash
PORT=8080 python app.py
```

### Aktive mode debug

```bash
DEBUG=true python app.py
```

### Chanje nimewo WhatsApp

Nan `templates/index.html`, modifye:
```html
<a href="https://wa.me/50942882076" ...>
```

Ranplase `50942882076` ak nimewo ou.

## ⚠️ Règ sekirite

L'application:

✅ **FÈ**:
- Bay enfòmasyon jeneral
- Klasifye gravite santòm yo
- Rekòmande pou wè doktè

❌ **PA FÈ**:
- Bay dyagnostik definitif
- Preskri medikaman
- Ranplase konsiltasyon medikal

**⚠️ ENPÒTAN**: Aplikasyon sa a pa ranplase yon doktè pwofesyonèl!

## 🔧 Pwoblèm komen

### Pwoblèm 1: ModuleNotFoundError

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Pwoblèm 2: Pa ka konekte sou mobile

- Verifye ou sou menm rezò WiFi
- Itilize adrès IP la pa `localhost`
- Verifye firewall pa bloke pò a

### Pwoblèm 3: Karakteri kreyòl pa afiche kòrèkteman

Asire w navigatè a sipòte UTF-8 encoding.

## 🌟 Amelyorasyon pou lavni

- [ ] Sipò pou plis lang (Espanyòl, Angle)
- [ ] Istorik konsiltasyon yo
- [ ] Ekspòte repons an PDF
- [ ] Videyo edikatif
- [ ] Lokalizatè klinik/lopital

## 📞 Sipò

Pou kesyon oswa pwoblèm:
- WhatsApp: +509 4288-2076
- Voye feedback atravè aplikasyon an

## 📜 Lisans

© 2026 Dòk GlorYah | Fèt pou Ayiti 🇭🇹

---

## 🇬🇧 English Version

### What is Dòk GlorYah?

Dòk GlorYah is a lightweight medical web application optimized for Haiti, using local AI to provide health advice in Haitian Creole.

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py

# Open in browser
# http://localhost:5000
```

### Features

- Local AI (no API required)
- Responds in Haitian Creole
- Mobile-optimized
- Automatic severity classification (🟢🟡🔴)
- WhatsApp contact integration
- Dark mode support
- Optimized for slow internet

### Safety

This app provides general information only and does not replace professional medical consultation.

---

**Fèt ak ❤️ pou Ayiti**
