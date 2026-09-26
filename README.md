# AI Novel Translator 📖🤖

Engine dan platform penerjemah web novel otomatis berbasis kecerdasan buatan (**AI/LLM**). Proyek ini dirancang untuk membaca, menerjemahkan, dan menyelaraskan bab novel dari bahasa asing (Jepang, Korea, Mandarin) ke dalam bahasa Indonesia secara kontekstual dan natural.

---

## ✨ Fitur Utama

- 🌐 **Context-Aware Translation**: Penerjemahan bab per bab dengan preservasi istilah khusus, nama karakter, dan gaya bahasa.
- ⚡ **Automated Batch Processing**: Proses penerjemahan otomatis banyak bab sekaligus dengan tracking progres.
- 📚 **Novel Reader Interface**: Penampil teks bacaan yang nyaman dengan tata letak minimalis.

---

## 📁 Struktur Direktori

```text
ai-novel-translator/
├── novel-translator/        # Inti aplikasi penerjemah novel
│   ├── core/                # Translation engine & parser
│   ├── tests/               # Unit testing & validasi terjemahan
│   ├── app.py               # Entry point aplikasi
│   └── requirements.txt     # Dependensi Python
└── README.md
```

---

## 🚀 Menjalankan Proyek

```bash
cd novel-translator
python -m venv venv
# Windows:
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
