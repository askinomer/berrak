#!/bin/bash
# Berrak canlı test: kurulum + çalıştırma (macOS ve Linux)
#
# Kullanım (Terminal'de):
#     bash ~/Downloads/berrak/canli_test_calistir.sh
#
# 1. Python 3.10 veya üstünü bulur.
# 2. Proje klasöründe bir sanal ortam (.venv) kurar ve gereken paketleri yükler.
# 3. Gemini anahtarı kayıtlı değilse sorar (yazarken görünmez) ve
#    .streamlit/secrets.toml dosyasına kaydeder; uygulama da bu dosyayı kullanır.
# 4. canli_test.py'yi çalıştırır. Sonuçlar canli_test_sonuclari/ klasörüne yazılır.

set -e
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 veya üstü bulunamadı."
  echo "https://www.python.org/downloads/ adresinden kurup bu komutu tekrar çalıştır."
  exit 1
fi
echo "Python: $("$PY" --version)"

if [ ! -x .venv/bin/python ]; then
  echo "Sanal ortam kuruluyor (ilk seferde 1-2 dakika sürebilir)..."
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
echo "Paketler hazır."

SECRETS=.streamlit/secrets.toml
if [ -z "$GEMINI_API_KEY" ] && ! grep -qs '^GEMINI_API_KEY *= *"AIza' "$SECRETS"; then
  echo
  echo "Gemini API anahtarı gerekli. Ücretsiz almak için: https://aistudio.google.com/apikey"
  read -r -s -p "Gemini API anahtarını yapıştır (ekranda görünmez) ve Enter'a bas: " G
  echo
  read -r -s -p "Tavily API anahtarı (yoksa sadece Enter): " T
  echo
  if [ -z "$G" ]; then
    echo "Anahtar girilmedi, çıkılıyor."
    exit 1
  fi
  mkdir -p .streamlit
  umask 077
  printf 'GEMINI_API_KEY = "%s"\nTAVILY_API_KEY = "%s"\n' "$G" "$T" > "$SECRETS"
  echo "Anahtarlar $SECRETS dosyasına kaydedildi (bu dosya GitHub'a yüklenmez)."
fi

echo
.venv/bin/python canli_test.py
echo
echo "Bitti. Sonuçlar canli_test_sonuclari/ klasöründe."
echo "Uygulamayı açmak için: .venv/bin/python -m streamlit run app.py"
