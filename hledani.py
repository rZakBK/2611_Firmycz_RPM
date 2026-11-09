"""
Mini vyhledávač firem – výukový projekt.

Dělá dvě věci:
  1) umožní si vyzkoušet vyhledávání (napíšeš dotaz, vypíše se pořadí firem),
  2) porovná dvě varianty řazení na sadě testovacích dotazů (dotazy.csv).

Varianta A: řadí jen podle toho, jak se dotaz shoduje s textem firmy.
Varianta B: totéž + bonus za vyšší hodnocení a více recenzí.

Spuštění:  python hledani.py
"""
import csv
import math
import os
import unicodedata
from datetime import datetime
from pathlib import Path
import pandas as pd

# ---------------------------------------------------------------------------
# 0) Barvy v terminálu
# ---------------------------------------------------------------------------
# Tento prázdný příkaz zapne ve Windows podporu barev v okně konzole.
os.system("")

TUCNE = "\033[1m"
ZELENA = "\033[92m"
CERVENA = "\033[91m"
SEDA = "\033[90m"
KONEC = "\033[0m"      # vrátí barvu zpět na normální

# ---------------------------------------------------------------------------
# 1) Načtení dat
# ---------------------------------------------------------------------------
# Složka, ve které leží tento skript. Soubory hledáme vždy v ní,
# ať se program spustí odkudkoli (dvojklikem, z VS Code, z terminálu).
SLOZKA = Path(__file__).parent

firmy = pd.read_csv(SLOZKA / "firmy.csv")      # tabulka všech firem
dotazy = pd.read_csv(SLOZKA / "dotazy.csv")    # testovací dotazy + správné odpovědi

SOUBOR_BEZ_VYSLEDKU = SLOZKA / "bez_vysledku.csv"   # sem se ukládají dotazy, které nic nenašly
SOUBOR_GRAF = SLOZKA / "ab_vysledky.png"             # sem se uloží graf porovnání A/B

# Váhy: shoda v oboru je důležitější než shoda v popisu
VAHY = {"obor": 3, "nazev": 2, "mesto": 2, "popis": 1}

# Slova, která nic nehledají, jen dotaz „zdobí“. Pravidlo „všechna slova
# se musí najít“ je přeskakuje (píšeme je bez diakritiky).
STOP_SLOVA = {"pro", "nejlepsi", "dobry", "dobra", "levny", "levne", "blizko", "okoli"}

# Časté české koncovky (bez diakritiky). Uřízneme je ze slov dotazu, aby
# „Brně“, „Brna“ i „Brnem“ hledaly stejně jako „Brno“. Delší koncovky jsou
# první, aby se z „Brnem“ uřízlo „em“, a ne jen „m“.
KONCOVKY = ("ami", "emi", "ech", "ich", "em", "ou", "om", "a", "e", "i", "u", "y", "o")

# Tvary, které uříznutí koncovky nevyřeší (mění se v nich i písmena uvnitř
# slova). Fungují jako malý slovník synonym: tvar z dotazu -> základní tvar.
VYJIMKY = {"praze": "praha", "plzni": "plzen", "plzne": "plzen"}

# Hezčí názvy pro výpis vysvětlení skóre
POPISKY = {"obor": "obor", "nazev": "název", "mesto": "město", "popis": "popis",
           "hodnoceni": "hodnocení", "recenze": "recenze"}


# ---------------------------------------------------------------------------
# 2) Pomocné funkce
# ---------------------------------------------------------------------------
def bez_diakritiky(text):
    """Odstraní diakritiku: 'Instalatér Říčany' -> 'Instalater Ricany'"""
    rozlozeny = unicodedata.normalize("NFD", text)
    return "".join(znak for znak in rozlozeny if unicodedata.category(znak) != "Mn")


def slova(text):
    """Rozdělí text na malá slova bez diakritiky a interpunkce: 'Pizza, těstoviny!' -> ['pizza', 'testoviny']"""
    cisty = bez_diakritiky(str(text).lower())
    cisty = "".join(znak if znak.isalnum() else " " for znak in cisty)
    return cisty.split()


def zakladni_tvar(slovo):
    """Zjednoduší české slovo na jeho základ: 'brne' -> 'brn', 'instalatera' -> 'instalater'.
    Koncovku uřízneme jen tehdy, když ze slova zůstanou aspoň 3 písmena."""
    slovo = VYJIMKY.get(slovo, slovo)      # nejdřív zkusíme slovník výjimek
    for koncovka in KONCOVKY:
        if slovo.endswith(koncovka) and len(slovo) - len(koncovka) >= 3:
            return slovo[:-len(koncovka)]
    return slovo


def podstatna_slova(dotaz):
    """Slova dotazu, která opravdu něco hledají: bez krátkých slov (v, na…) a bez stop slov,
    zkrácená na základní tvar."""
    return [zakladni_tvar(s) for s in slova(dotaz) if len(s) >= 3 and s not in STOP_SLOVA]


def skore_textu(dotaz, firma):
    """Spočítá, jak moc se dotaz shoduje s firmou. Vrací dvojici (skóre, rozpis).

    Za každé slovo z dotazu, kterým začíná nějaké slovo v daném údaji firmy, přičteme váhu údaje.
    Pravidlo: KAŽDÉ podstatné slovo dotazu se musí ve firmě někde najít.
    Když se některé nenajde, firma do výsledků nepatří (skóre 0)."""
    skore = 0
    rozpis = {}                            # např. {"obor": 3, "mesto": 2}
    for slovo_dotazu in podstatna_slova(dotaz):
        nalezeno = False
        for udaj, vaha in VAHY.items():
            if any(slovo.startswith(slovo_dotazu) for slovo in slova(firma[udaj])):
                skore += vaha
                rozpis[udaj] = rozpis.get(udaj, 0) + vaha
                nalezeno = True
        if not nalezeno:                   # toto slovo firma vůbec neobsahuje
            return 0, {}
    return skore, rozpis


def skore_a(dotaz, firma):
    """Varianta A: jen shoda textu."""
    return skore_textu(dotaz, firma)


def skore_b(dotaz, firma):
    """Varianta B: shoda textu + bonus za hodnocení a počet recenzí.
    Bonus dostanou jen firmy, které se s dotazem shodují."""
    text, rozpis = skore_textu(dotaz, firma)
    if text == 0:
        return 0, {}
    bonus_hodnoceni = 0.4 * firma["hodnoceni"]
    bonus_recenze = 0.4 * math.log10(1 + firma["pocet_recenzi"])
    rozpis["hodnoceni"] = bonus_hodnoceni
    rozpis["recenze"] = bonus_recenze
    return text + bonus_hodnoceni + bonus_recenze, rozpis


def hledej(dotaz, varianta="A", kolik=5):
    """Vrátí seřazený seznam firem pro daný dotaz (včetně sloupců skore a rozpis)."""
    funkce = skore_a if varianta == "A" else skore_b
    vysledky = firmy.copy()
    spocitano = [funkce(dotaz, firma) for _, firma in vysledky.iterrows()]
    vysledky["skore"] = [skore for skore, _ in spocitano]
    vysledky["rozpis"] = [rozpis for _, rozpis in spocitano]
    vysledky = vysledky[vysledky["skore"] > 0]                      # jen firmy, které se shodují
    vysledky = vysledky.sort_values("skore", ascending=False)       # nejlepší nahoru
    return vysledky.head(kolik)


def slova_oboru(dotaz):
    """Vrátí z dotazu jen slova, která odpovídají nějakému oboru v katalogu.
    Z 'autoservis Brno' zůstane 'autoservis' (Brno není obor)."""
    vsechny_obory = set()
    for obor in firmy["obor"]:
        vsechny_obory.update(slova(obor))
    vybrana = []
    for slovo in slova(dotaz):
        if len(slovo) < 3 or slovo in STOP_SLOVA:
            continue
        zaklad = zakladni_tvar(slovo)
        if any(o.startswith(zaklad) for o in vsechny_obory):
            vybrana.append(slovo)
    return " ".join(vybrana)


def rozpis_textem(rozpis):
    """{'obor': 3, 'hodnoceni': 1.88} -> 'obor +3, hodnocení +1.9'"""
    return ", ".join(f"{POPISKY[udaj]} +{round(body, 1)}" for udaj, body in rozpis.items())


def zaznamenej_bez_vysledku(dotaz):
    """Připíše dotaz, který nic nenašel, do souboru bez_vysledku.csv (s datem a časem)."""
    novy_soubor = not SOUBOR_BEZ_VYSLEDKU.exists()
    with open(SOUBOR_BEZ_VYSLEDKU, "a", newline="", encoding="utf-8") as soubor:
        zapis = csv.writer(soubor)
        if novy_soubor:
            zapis.writerow(["cas", "dotaz"])                       # hlavička jen poprvé
        zapis.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), dotaz])


# ---------------------------------------------------------------------------
# 3) Vyzkoušení vyhledávání
# ---------------------------------------------------------------------------
def vyzkouset():
    print("\nZkuste např.: instalatér Brno, pizza Blansko, kadeřnictví Praha")
    print("(prázdný řádek = návrat do menu)\n")
    while True:
        dotaz = input("Co hledáte? ").strip()
        if dotaz == "":
            break
        hledany = dotaz
        if hledej(dotaz).empty:
            # Přesně nic nenalezeno. Dotaz si uložíme a zkusíme hledat jen podle oboru.
            zaznamenej_bez_vysledku(dotaz)
            jen_obor = slova_oboru(dotaz)
            if jen_obor and not hledej(jen_obor).empty:
                print(f"\n  {CERVENA}Pro „{dotaz}“ nic přesně neodpovídá.{KONEC}")
                print(f"  Zobrazuji výsledky jen pro „{jen_obor}“ (jiná města):")
                hledany = jen_obor
        for varianta in ["A", "B"]:
            print(f"\n  {TUCNE}Varianta {varianta}:{KONEC}")
            vysledky = hledej(hledany, varianta)
            if vysledky.empty:
                print(f"    {CERVENA}nic nenalezeno{KONEC}")
            for poradi, (_, f) in enumerate(vysledky.iterrows(), start=1):
                print(f"    {poradi}. {f['nazev']} ({f['mesto']}, {f['hodnoceni']} ★, {f['pocet_recenzi']} recenzí)")
                print(f"       {SEDA}proč: {rozpis_textem(f['rozpis'])} = {round(f['skore'], 1)}{KONEC}")
        print()


def prehled_dat():
    """Vypíše, jaké obory jsou v datech a ve kterých městech."""
    print(f"\n{TUCNE}Přehled dat: {len(firmy)} firem{KONEC}\n")
    for obor, skupina in firmy.groupby("obor"):
        mesta = ", ".join(sorted(skupina["mesto"].unique()))
        print(f"  {TUCNE}{obor}{KONEC} ({len(skupina)}): {mesta}")
    print()


# ---------------------------------------------------------------------------
# 4) Vyhodnocení na testovacích dotazech
# ---------------------------------------------------------------------------
def nakresli_graf(prumery):
    """Uloží sloupcový graf porovnání variant A a B do souboru ab_vysledky.png."""
    try:
        import matplotlib
        matplotlib.use("Agg")              # graf jen uložíme do souboru, nic se neotevírá
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"{SEDA}Graf se nevytvořil: chybí knihovna matplotlib (pip install matplotlib).{KONEC}")
        return

    metriky = ["přesnost@5", "první správná"]
    hodnoty_a = [prumery["presnost_A"], prumery["mrr_A"]]
    hodnoty_b = [prumery["presnost_B"], prumery["mrr_B"]]
    pozice = range(len(metriky))
    sirka = 0.35

    fig, ax = plt.subplots(figsize=(6, 4))
    sloupce_a = ax.bar([p - sirka / 2 for p in pozice], hodnoty_a, sirka, label="Varianta A", color="#9aa5b1")
    sloupce_b = ax.bar([p + sirka / 2 for p in pozice], hodnoty_b, sirka, label="Varianta B", color="#cc0000")
    ax.bar_label(sloupce_a, fmt="%.2f")
    ax.bar_label(sloupce_b, fmt="%.2f")
    ax.set_xticks(list(pozice), metriky)
    ax.set_ylim(0, 1.1)
    ax.set_title("Porovnání variant řazení A a B")
    ax.legend()
    fig.tight_layout()
    fig.savefig(SOUBOR_GRAF, dpi=150)
    plt.close(fig)
    print(f"Graf uložen do souboru {SOUBOR_GRAF.name}")


def vypis_bez_vysledku():
    """Vypíše, které dotazy uživatelů zatím nic nenašly a kolikrát."""
    if not SOUBOR_BEZ_VYSLEDKU.exists():
        print("Zatím nebyl uložen žádný dotaz bez výsledku.")
        return
    zaznamy = pd.read_csv(SOUBOR_BEZ_VYSLEDKU)
    print(f"Dotazy bez výsledku z vyzkoušení (celkem {len(zaznamy)}):")
    for dotaz, pocet in zaznamy["dotaz"].value_counts().items():
        print(f"  {CERVENA}{dotaz}{KONEC} ({pocet}×)")


def vyhodnotit():
    vysledky = []
    for _, radek in dotazy.iterrows():
        spravne = {int(x) for x in str(radek["spravne_id"]).split(";")}
        zaznam = {"dotaz": radek["dotaz"]}
        for varianta in ["A", "B"]:
            top5 = list(hledej(radek["dotaz"], varianta, kolik=5)["id"])
            trefy = sum(1 for id_firmy in top5 if id_firmy in spravne)
            # přesnost@5: kolik z prvních 5 výsledků je správných (0 až 1)
            zaznam[f"presnost_{varianta}"] = trefy / 5
            # na kterém místě je první správná firma (1 = nejlepší); 0 = vůbec ne
            prvni = next((i for i, id_firmy in enumerate(top5, 1) if id_firmy in spravne), None)
            zaznam[f"mrr_{varianta}"] = 1 / prvni if prvni else 0
            if varianta == "A":
                zaznam["nalezeno"] = len(top5)   # kolik výsledků dotaz vůbec vrátil
        vysledky.append(zaznam)
    tabulka = pd.DataFrame(vysledky)
    pd.set_option("display.width", 120)
    print("\nVýsledky po jednotlivých dotazech:\n")
    print(tabulka.round(2).to_string(index=False))

    prumery = tabulka[["presnost_A", "mrr_A", "presnost_B", "mrr_B"]].mean()
    print(f"\n{TUCNE}Průměr přes všechny dotazy:{KONEC}")
    for varianta in ["A", "B"]:
        jina = "B" if varianta == "A" else "A"
        lepsi = prumery[f"presnost_{varianta}"] > prumery[f"presnost_{jina}"]
        barva = ZELENA if lepsi else ""
        print(f"  {barva}Varianta {varianta}: přesnost@5 = {prumery[f'presnost_{varianta}']:.2f}, "
              f"první správná = {prumery[f'mrr_{varianta}']:.2f}{KONEC}")

    prazdne = tabulka[tabulka["nalezeno"] == 0]["dotaz"].tolist()
    print(f"\nTestovací dotazy bez jediného výsledku: {len(prazdne)}")
    for dotaz in prazdne:
        print(f"  {CERVENA}{dotaz}{KONEC}")

    print()
    vypis_bez_vysledku()
    print()
    nakresli_graf(prumery)
    print()


# ---------------------------------------------------------------------------
# 5) Spuštění
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"{TUCNE}Mini vyhledávač firem{KONEC}")
    print("Ukázkový projekt k pozici Ranking Product Manager (Firmy.cz)")

    # Menu se opakuje, dokud uživatel nezvolí konec.
    while True:
        print()
        print("  1 = vyzkoušet vyhledávání")
        print("  2 = vyhodnotit varianty A a B na testovacích dotazech")
        print("  3 = přehled dat (jaké obory jsou ve kterých městech)")
        print("  Enter = konec")
        volba = input("Vyberte 1, 2 nebo 3: ").strip()
        if volba == "":
            break
        try:
            if volba == "1":
                vyzkouset()
            elif volba == "2":
                vyhodnotit()
            elif volba == "3":
                prehled_dat()
            else:
                print("Neplatná volba.")
        except Exception as chyba:
            # Když se něco pokazí, vypíšeme chybu a vrátíme se do menu
            print(f"\n{CERVENA}Nastala chyba: {chyba}{KONEC}")
