# NEEDS NATIVE CHECK

# LinkedIn sequence, dansk, marked `dk`

Denmark. Starter 8. september 2026.

Dansk og litauisk tekst er skrevet af en ikke-modersmålstalende og er **ikke**
korrekturlæst af en dansker. Læs den igennem, og send den derefter til en
modersmålstalende, før den bliver sendt til nogen. Se `BLOCKED.md` B10.

**Loft: 20 kontaktanmodninger om dagen.** Det er `linkedin-automator`s
eksisterende grænse. `build_linkedin_queue.py` håndhæver den.

**Kold e-mail findes ikke i dette marked.** Dansk markedsføringslov er strengere
end resten af EU på uanmodet kommerciel e-mail, så danske adresser kommer aldrig
i Instantly. LinkedIn og telefon er upåvirkede, og telefon er den kanal, der
erstatter e-mailen her. Se `sequences/phone/da.md`.

Segmentlinjerne ligger i `config/hooks.yaml`. Revisionsvarianten står skrevet ud
herunder, fordi det er det største segment. Forsikring og bolig følger efter.

## UTM

Skabelonen, præcis som kampagnespecifikationen skriver den:

```
?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content={market}_{step}
```

Kun trin 3 og 4 har et link. Her er `{market}` lig `dk`:

```
https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=dk_3
https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=dk_4
```

## Fakta, teksten må bruge

89 dollar pr. bruger om måneden plus 500 dollar i opstart, som dækker workshop,
onboarding og opsætning. Fra 10 brugere. To ugers gratis pilot med workshop og
opsætning inkluderet, betaling starter på dag 14. Det kører inde i Outlook. Det
sender aldrig noget af sig selv. Det kører i Europa.

Afkasttallene (cirka 9 gange, omkring 400 euro om måneden, tjent hjem på cirka
40 dage) er MODELLEREDE, ikke målte. De kommer fra en model, der antager et fast
antal sparede minutter pr. person pr. dag. Ingen kunde har rapporteret dem.
Teksten må bruge dem som et regneeksempel, og kun når den siger det i samme
sætning. Skriv aldrig, at firmaer sparer, ser, får eller rapporterer dem.

Der findes ingen udtalelser fra kunder og ingen navngivne pilotkunder. Find ikke
på nogen. Hvor social proof normalt ville stå, siger teksten ærligt, at der ikke
er nogen endnu, og viser modellen i stedet.

---

## Trin 1. Kontaktanmodning. Dag 0.

Under 300 tegn. Ingen salgstale, intet link.

> Hej Mette. Jeg arbejder med revisionsfirmaer og den bunke kundemails, der
> vokser i ugerne op mod en frist. Vil gerne forbindes.

Segmentvarianter:

- **Forsikring:** Hej Mette. Jeg arbejder med forsikringsmæglere og kundemailen
  omkring skader og fornyelser. Vil gerne forbindes.
- **Bolig og ejendom:** Hej Mette. Jeg arbejder med ejendoms- og
  boligadministratorer og den beboer- og bestyrelsesmail, der fylder kontorets
  indbakke. Vil gerne forbindes.

Mangler fornavnet, så drop det og start ved "Jeg arbejder med". Skriv aldrig
"Hej der".

---

## Trin 2. To dage efter de har accepteret.

En linje om smerten, et spørgsmål. Intet link, intet produktnavn.

> Ugen før en frist kommer de samme fire spørgsmål fra kunderne igen og igen, og
> de skal alle sammen stadig besvares skriftligt.
>
> Hvordan klarer I den periode hos Revision Nord?

Segmentvarianter:

- **Forsikring:** En skade bliver anmeldt, og kunden vil have en opdatering hver
  anden dag på skrift, mens selskabet tager sin tid. Fornyelser gør det samme
  hvert kvartal. Hvem ender med at skrive de fleste af de opdateringer hos
  Revision Nord?
- **Bolig og ejendom:** Beboere og bestyrelsesmedlemmer skriver til kontoret
  hele dagen, og det meste er de samme få spørgsmål om husleje, reparationer og
  fraflytning. Hvor mange hos Revision Nord sidder i den indbakke på en
  almindelig dag?

Svarer de, så stop sekvensen og skriv som et menneske. Resten af trinnene er
til tavshed, ikke til samtale.

---

## Trin 3. Dag 5.

Linket, sat op som det, der forklarer det hurtigere end endnu en besked.

> Tak, Mette. Jeg laver ikke det her om til en salgstale i din indbakke.
>
> Kort fortalt: vi lægger jeres egne svar ind i Outlook, så mailen allerede er
> skrevet, når nogen åbner den. Jeres ordlyd, ikke vores, og der bliver ikke
> sendt noget, før et menneske har læst det.
>
> Jeg har lavet en side, der forklarer det hurtigere, end jeg kan i en besked:
> https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=dk_3
>
> Er det ikke noget for jer, så sig til, og jeg lader jer være.

Den sidste linje bliver stående. Den koster én sætning og er forskellen på en
sekvens og en plage.

---

## Trin 4. Dag 12. Sidste henvendelse.

Kort, ét tal, en video, og et rigtigt farvel.

> Sidste besked fra mig. En kort video, der viser, hvordan det ser ud inde i
> Outlook. Ingen opsætning, ingen ny app:
> https://teams.doviloop.dev/?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4&utm_content=dk_4
>
> Ét tal, og det er en model, ikke et kundetal, for ingen har målt det endnu:
> antag cirka tyve minutter sparet om dagen pr. person, så lander et team på ti
> på omkring 400 euro om måneden, og opstarten er tjent hjem på cirka seks uger.
> De første to uger er gratis, og vi laver opsætningen, så det eneste, det koster
> jer i starten, er en eftermiddag til workshoppen.
>
> Passer timingen ikke, så passer den ikke. Held og lykke med sæsonen.

Vedhæft ugens danske reel. Send ikke trin 4 uden den.

---

## Regler til den, der kører sekvensen

1. Stop sekvensen i samme øjeblik et menneske svarer overhovedet noget.
2. Aldrig to trin samme dag.
3. Tyve kontaktanmodninger om dagen på tværs af alle tre markeder, ikke pr.
   marked.
4. Ser de ud til at være under 10 personer, når du åbner profilen, så spring dem
   over. Tilbuddet starter ved 10 brugere.
5. Skriv ikke prisen i en besked. Den står på siden.
6. Ingen kold e-mail til danske adresser. Kanalen her er LinkedIn og telefon.
