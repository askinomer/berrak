# Bu dosya, testlerin proje kök klasöründen "berrak" ve "canli_test" modüllerini
# bulabilmesi için pytest'e kök klasörü gösterir.

# canli_test.py adı "*_test.py" kalıbına uyduğu için pytest onu test sanmasın;
# o dosya gerçek API'lerle elle çalıştırılan bir betik.
collect_ignore = ["canli_test.py"]
