# WebDollar Miner — manual de utilizare

Aplicație cu fereastră (interfață grafică) pentru minat WebDollar într-un
pool, fără să fie nevoie de nodul complet WebDollar. Nu necesită nimic
instalat în plus pe calculator — instalatorul aduce tot ce are nevoie,
inclusiv componenta WebView2 (dacă nu e deja pe sistem).

## Cerințe

- Windows 10 sau 11, 64-bit.
- Un portofel WebDollar (fișier `.webd`). Dacă nu ai unul, cere-i persoanei
  de la care ai primit programul unul de test, sau folosește un portofel
  propriu, dedicat minatului (nu portofelul principal cu fonduri mari).

## Instalare

1. Rulează fișierul instalator (`WebDollar Miner_0.1.0_x64_en-US.msi`).
2. Urmează pașii instalatorului (Next → Next → Install).
3. La final, aplicația se poate lansa automat, sau o găsești în meniul
   Start, sub "WebDollar Miner".

## Pornirea minatului

La prima pornire vezi un formular:

| Câmp | Ce pui |
|---|---|
| **Portofel (.webd)** | Calea către fișierul tău de portofel. Apasă "Răsfoiește…" ca să-l alegi vizual, sau scrie calea direct (ex. `C:\WEBD\portofelul-meu.webd`). |
| **Parolă portofel** | Completează DOAR dacă portofelul tău e criptat cu parolă. Lasă gol altfel. |
| **Pool — URL** | Vine deja completat cu pool-ul WebDollar RunPlace. Nu e nevoie să schimbi, decât dacă vrei alt pool. |
| **Pool — cheie publică** | La fel, vine deja completată. |

Apasă **„Start minerit”**. Zona de dedesubt arată indicatori live:

- **Conectat / Deconectat** — starea legăturii cu pool-ul.
- **Înălțime** — blocul curent al rețelei.
- **Heartbeats** — câte rapoarte ai trimis către pool.
- **Potriviri reale** — de câte ori ai găsit chiar un bloc (rar, e normal
  să rămână 0 ore/zile).
- **Reward** — recompensa ta, în curs de acumulare.
- **Confirmed** — recompensa deja confirmată de pool (ce vei primi la plată).

Jos, în zona de log, vezi textul brut, linie cu linie, util dacă vrei să
verifici exact ce se întâmplă sau dacă apare o eroare.

**Important:** recompensa crește LENT, mai ales cu balanțe mici — poate
dura ore pentru ca „Confirmed” să se miște vizibil. Nu e un semn că
programul nu funcționează, e normal (depinde de durata ciclului de
recompensă al pool-ului și de mărimea balanței tale).

## Oprirea minatului

Apasă **„Stop”** în fereastră. Minatul se oprește, dar aplicația rămâne
pornită (poți reporni oricând, cu alt portofel dacă vrei).

## Minimizare în system tray

- Închiderea ferestrei (butonul X) **NU** oprește aplicația — doar ascunde
  fereastra. Minatul continuă în fundal.
- Cauți iconița aplicației în system tray (colțul din dreapta jos al barei
  de task-uri Windows, lângă ceas).
- **Click pe iconiță** — arată/ascunde fereastra.
- **Click dreapta pe iconiță** — apare un meniu cu:
  - „Arată / Ascunde” — același efect ca click simplu.
  - „Ieșire (oprește și minerul)” — **asta e singurul mod de a închide
    efectiv aplicația și de a opri minatul complet.**

## Probleme frecvente

- **„Minerul rulează deja — apasă Stop întâi.”** — ai apăsat Start de două
  ori; apasă Stop, apoi Start din nou.
- **„Decriptare eșuată”** (în zona de log) — parola portofelului e greșită.
- **Nu se conectează deloc** — verifică conexiunea la internet, sau dacă
  portofelul minează deja din altă parte în acest moment (nu rulează două
  instanțe pe aceeași adresă simultan).
