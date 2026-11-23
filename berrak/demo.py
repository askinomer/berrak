"""API anahtarı olmadan arayüzü gösterebilmek için hazır örnek içerik.

Sunumda internet veya kota sorunu çıkarsa yedek olarak da kullanılabilir.
"""

from .llm import BerrakIcerik
from .pipeline import Result, _finish

DEMO_TOPIC = "Fotosentez nedir?"

# Ateşman karşılaştırması için ansiklopedik üslupta yazılmış örnek "kaynak" metni
DEMO_ORIGINAL = (
    "Fotosentez, klorofil pigmentine sahip olan bitkiler, algler ve bazı bakteriler tarafından "
    "güneş ışığından elde edilen enerjinin kullanılmasıyla, atmosferden alınan karbondioksit ile "
    "kökler vasıtasıyla topraktan emilen suyun, kloroplast organellerinde gerçekleşen bir dizi "
    "biyokimyasal tepkime neticesinde glikoz gibi organik bileşiklere dönüştürülmesi sürecidir. "
    "Işığa bağımlı tepkimeler tilakoit zarlarında meydana gelirken, ışıktan bağımsız tepkimeler "
    "olarak da adlandırılan Calvin döngüsü stromada gerçekleştirilmektedir. Bu süreç sonucunda "
    "yan ürün olarak açığa çıkan oksijenin atmosfere verilmesi, aerobik solunum yapan canlıların "
    "yaşamlarını sürdürebilmeleri açısından vazgeçilmez bir öneme sahip bulunmaktadır."
)

DEMO_SOURCES = [
    {"title": "Fotosentez – Vikipedi", "url": "https://tr.wikipedia.org/wiki/Fotosentez", "content": DEMO_ORIGINAL},
]

DEMO_CONTENT = BerrakIcerik.model_validate({
    "baslik": "Fotosentez nedir?",
    "kisaca": [
        "Fotosentez, bitkilerin kendi besinini üretmesidir. [1]",
        "Bitkiler bunun için **güneş ışığı**, su ve karbondioksit kullanır. [1]",
        "Sonunda şeker ve **oksijen** oluşur. [1]",
    ],
    "bolumler": [
        {
            "baslik": "Fotosentez ne demek?",
            "ozet": "Fotosentez, ışık yardımıyla besin yapmak demektir.",
            "paragraflar": [
                "Kelime iki parçadan oluşur. \"Foto\" ışık demektir. \"Sentez\" ise birleştirmek demektir.",
                "Bitkiler bizim gibi yemek yiyemez. Bu yüzden besinlerini **kendileri üretir**. [1]",
            ],
            "maddeler": [],
        },
        {
            "baslik": "Bitkinin nelere ihtiyacı var?",
            "ozet": "Fotosentez için 3 şey gerekir.",
            "paragraflar": [
                "Bir de yeşil bir madde gerekir. Bu maddenin adı **klorofil**. Klorofil ışığı yakalar. [1]",
            ],
            "maddeler": [
                "**Güneş ışığı** enerjiyi verir.",
                "**Su** kökler yoluyla topraktan gelir. [1]",
                "**Karbondioksit** havadan gelir. [1]",
            ],
        },
        {
            "baslik": "Fotosentez nasıl olur?",
            "ozet": "Fotosentez yaprakta adım adım olur.",
            "paragraflar": [
                "Yaprağın içinde çok küçük yapılar var. Bunlara **kloroplast** denir. İşin çoğu burada yapılır. [1]",
            ],
            "maddeler": [
                "Klorofil güneş ışığını yakalar.",
                "Bitki bu ışığın enerjisini kullanır.",
                "Su ve karbondioksit birleşir.",
                "Sonunda glikoz ve oksijen oluşur. [1]",
            ],
        },
        {
            "baslik": "Neden önemli?",
            "ozet": "Fotosentez olmadan canlılar yaşayamaz.",
            "paragraflar": [
                "Bitkiler oksijeni havaya bırakır. Biz de bu oksijenle **nefes alırız**. [1]",
                "Hayvanlar bitkileri yer. Böylece besin onlara geçer. Yani besin zinciri fotosentezle başlar.",
            ],
            "maddeler": [],
        },
    ],
    "sozluk": [
        {"terim": "Klorofil", "aciklama": "Bitkiye yeşil rengini veren madde. Işığı yakalar."},
        {"terim": "Kloroplast", "aciklama": "Bitki hücresinde fotosentezin yapıldığı küçük yapı."},
        {"terim": "Karbondioksit", "aciklama": "Havada bulunan bir gaz. Biz nefes verirken de çıkar."},
        {"terim": "Glikoz", "aciklama": "Bitkinin ürettiği bir tür şeker. Bitkiye enerji verir."},
    ],
    "akilda_kalsin": "Bitkiler güneş ışığıyla su ve karbondioksitten besin ve oksijen üretir.",
    "eksik_bilgi": "",
})


def demo_result() -> Result:
    return _finish(DEMO_CONTENT, DEMO_SOURCES, DEMO_ORIGINAL, engine="Demo", model="—",
                   queries=[DEMO_TOPIC], is_demo=True)
