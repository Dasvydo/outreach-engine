# NEEDS NATIVE CHECK

# Telefon, dansk, marked `dk`. Primær kanal.

Én side. Læs den før du ringer, ikke mens du ringer.

Tekst skrevet af en ikke-modersmålstalende og **ikke** korrekturlæst af en
dansker. Se `BLOCKED.md` B10.

**Hvorfor telefon er den vigtige kanal her.** Dansk markedsføringslov er
strengere end resten af EU på uanmodet kommerciel e-mail, så der går ingen danske
adresser i Instantly. Telefon er det, der træder i stedet for kold e-mail i
Danmark, og danske firmaer i dette segment tager telefonen. Kanalen starter
8. september 2026, samtidig med LinkedIn.

## UTM

Skabelonen, præcis som kampagnespecifikationen skriver den:

```
?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content={market}_{step}
```

Et opkald er ikke et klik. Linket her lever i opfølgningsmailen, du sender bagefter
til en, du lige har talt med, så kilden og mediet er den kanal, der faktisk
sendte klikket. Kampagne og indhold er uændrede:

```
https://teams.doviloop.dev/?utm_source=phone&utm_medium=call&utm_campaign=teams_q4&utm_content=dk_1
```

Trinnummeret er det opkald i rækken, du er nået til. Første opkald er `dk_1`,
opfølgende opkald er `dk_2`.

## Før du ringer

Kig på firmaet i to minutter. Du skal have ét konkret forhold i hovedet: et
segment, en størrelse og noget fra deres egen hjemmeside. Ring aldrig blindt.

Ring mellem 9 og 11 eller mellem 13 og 15. Ikke fredag eftermiddag. Ikke i ugen
op mod en frist, hvis du ringer til revisorer, for det er præcis den uge,
samtalen handler om.

Du sælger ikke i telefonen. Du booker femten minutter.

---

## Åbningen

Sig hvem du er, hvorfor du ringer, og giv dem en vej ud med det samme.

> Hej, det er Dovy fra DoviLoop. Jeg arbejder med revisionsfirmaer og den
> kundemail, der hober sig op før en frist. Et hurtigt spørgsmål, så slipper jeg
> dig igen. Har du et halvt minut?

Segmentvarianter til den midterste sætning:

- **Forsikring:** Jeg arbejder med mæglere og kundemailen omkring skader og
  fornyelser.
- **Bolig og ejendom:** Jeg arbejder med ejendomsadministratorer og den
  beboermail, der fylder kontorets indbakke.

Hvis de siger ja, kommer spørgsmålet. Ét spørgsmål, ikke tre.

> Hvor mange hos jer sidder og skriver kundemails i løbet af en dag?

Er svaret under ti, så tak dem og læg på. Det er ikke et tab. Tilbuddet starter
ved ti brugere, og de har ikke fortjent fem minutters salgstale, de ikke kan
bruge til noget.

Er svaret ti eller derover:

> Så kender du sikkert det her. Det er de samme fem spørgsmål hver uge, og de
> skal alle sammen stadig besvares skriftligt. Vi lægger jeres egne svar ind i
> Outlook, så mailen allerede er skrevet, når nogen åbner den. Jeres ordlyd. Der
> bliver ikke sendt noget, før et menneske har læst det.
>
> Det er ikke noget, jeg kan vise i telefonen. Har du et kvarter i næste uge?

Så tier du stille. Lad dem svare.

---

## De tre afvisninger, du får

### 1. "Vi har ikke tid lige nu."

Det er sandt, og det er ofte hele pointen. Skub ikke.

> Det er faktisk grunden til, at jeg ringer, men jeg forstår, at det ikke hjælper
> i dag. Skal jeg ringe igen om tre uger, når fristen er overstået? Jeg sender
> ikke andet imens.

Og så gør du præcis det. Sæt det i kalenderen mens I taler.

### 2. "Vi bruger allerede noget" eller "det klarer vi selv."

Vær ikke uenig. Spørg til det.

> Fint, hvad bruger I? … Ja, det dækker en del af det. Det, folk plejer at mangle,
> er, at svarene skal være jeres egne, altså jeres priser, jeres frister, jeres
> formuleringer, og at det ligger inde i Outlook, hvor de allerede arbejder. Det
> er den del, vi laver. Er det noget, I har fået løst?

### 3. "Send noget på mail."

Det betyder tit nej. Behandl det som et rigtigt svar, og gør det billigt for dem.

> Det gør jeg gerne. Jeg sender én mail med et link til en side, der forklarer
> det på to minutter, og en video, der viser det inde i Outlook. Hvis du efter
> det synes, det er noget, så booker du selv et tidspunkt på siden. Hører jeg
> ikke fra dig, så lader jeg det ligge. Er det i orden?

Send den mail samme dag med linket ovenfor. Én mail. Ikke tre.

---

## Hvis de spørger om prisen

Sig den. Undvig aldrig et prisspørgsmål i telefonen, det koster mere tillid, end
tallet koster.

> 89 dollar pr. bruger om måneden, og 500 dollar i opstart, som dækker workshop,
> opsætning og onboarding. Fra ti brugere. De første to uger er gratis og
> inkluderer det hele, så I kan se det virke, før der bliver trukket noget.

## Hvis de spørger om andre kunder

Der er ingen navngivne kunder og ingen udtalelser endnu. Find ikke på nogen.

> Jeg har ingen navne, jeg må bruge endnu, og jeg vil hellere sige det, end finde
> på noget. Det, jeg har, er tallene: omkring 400 euro sparet om måneden pr.
> team, og opstarten tjent hjem på cirka 40 dage.

## Efter opkaldet

Skriv det i `campaign.touches` med kanal `phone`, trinnummeret og udfaldet samme
dag. Gør du det ikke, findes opkaldet ikke, når A/B-testen skal læses.
