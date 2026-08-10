# Onboarding voor friends-and-family

Status: de persistente website-onboarding en HTTPS-eigendomsverificatiefundering zijn lokaal en op
staging geaccepteerd in Release 14 fase A. De begeleide verificatie-interface en veilige
tokenvernieuwing zijn lokaal en op staging geaccepteerd in fase B. De veilige, idempotente eerste
crawl is lokaal en op staging geaccepteerd in fase C. Begrijpelijke voortgang en end-to-end
gebruikersacceptatie volgen in afzonderlijke fasen.

## Doel

Een uitgenodigde niet-technische gebruiker moet zonder terminal-, database- of handmatige
beheerdercorrectie van uitnodiging naar een geverifieerde website en begrijpelijke eerste
crawlresultaten kunnen gaan. De eerste release blijft invitation-only; publieke zelfregistratie is
geen voorwaarde voor deze mijlpaal.

## Bestaande basis

De applicatie ondersteunt al:

- persoonlijke accounts, sessielogin en rollen;
- eenmalige uitnodigingslinks en toegang per klant;
- beheer van organisatieleden en intrekken van toegang;
- atomair aanmaken van klant, website, website-instellingen en eerste volledige crawljob;
- bescherming tegen dubbele klantnamen en onboarding tijdens een deployment-drain;
- zichtbare crawlstatus en blijvende selectie van klant en website in de browser;
- tests voor atomair aanmaken, normalisatie, dubbele invoer, login en uitnodigingen.

Deze onderdelen vormen nog geen volledige eindgebruikersonboarding. Het bestaande formulier is
vooral een beheerfunctie en heeft geen blijvende wizardstatus of eigendomsverificatie.

## Minimale invitation-only flow

1. Een beheerder maakt via de interface een organisatie en uitnodiging aan.
2. De ontvanger opent de eenmalige link, kiest een wachtwoord en krijgt toegang tot die organisatie.
3. Een begeleide wizard vraagt websitenaam, basis-URL, sitemap en veilige crawlvoorkeuren.
4. De gebruiker bewijst website-eigendom via één ondersteunde verificatiemethode.
5. De gebruiker kan een analyticsbron koppelen en gekwalificeerde leadevents definiëren. Bij een
   koppeling voert het systeem een meetkwaliteitscontrole uit voordat conversie-inzichten als
   betrouwbaar worden aangemerkt.
6. Na succesvolle websiteverificatie maakt het systeem de eerste volledige crawl exact eenmaal aan.
7. De wizard toont wachtrij, voortgang, eventuele herstelbare fout en uiteindelijk de eerste
   resultaten met één duidelijke vervolgstap.
8. Na uitloggen, refresh of browserwissel hervat de gebruiker bij de laatst voltooide stap.

## Meetkwaliteit tijdens onboarding

Een analyticskoppeling is niet verplicht om crawling en technische monitoring te starten. Zodra
GA4, Matomo of een latere analyticsbron wordt gekoppeld, wordt meetvalidatie wel een vast onderdeel
van onboarding en een voorwaarde voor betrouwbare conversie-inzichten.

De onboarding controleert minimaal:

1. **Koppeling en scope:** juiste property of site, domein, rechten, tijdzone, recente data en
   bruikbare periode-overlap met andere gekoppelde bronnen.
2. **Meetdefinitie:** geselecteerde gekwalificeerde leadevents, onderscheid tussen primaire
   conversies en microconversies, verwachte trigger en ingangsdatum van de definitie.
3. **Historische nulmeting:** bij voorkeur 60–90 dagen controleren op event-/sessieverhoudingen,
   dubbele events, abrupte pieken, events zonder sessies, onlogische landingspagina's,
   bedankpagina's en veilige URL-varianten. Gebruik websitehistorie en vergelijkbare pagina's; geen
   universele conversiedrempel.
4. **Validatiestatus:** toon `verbonden — nog niet gevalideerd`, `metingen betrouwbaar`, `aandacht
   nodig` of `onvoldoende gegevens`, inclusief bewijs, meetperiode en eerstvolgende controle.

Verdachte events blijven als ruwe brondata zichtbaar en worden niet automatisch verwijderd of
gecorrigeerd. Afhankelijke conversie-inzichten tonen een lagere confidence en waar mogelijk een
gevoeligheidsberekening met en zonder de verdachte bijdrage. Bij onvoldoende historie herhaalt het
systeem de controle na 7, 14 en 30 dagen.

Een meetprobleem wordt als afzonderlijke, gededupliceerde analytics-kwaliteitscontrole opgeslagen
en volgt de normale issue-lifecycle. Het blokkeert technische onboarding of crawling niet, maar wel
de kwalificatie `betrouwbaar` voor afhankelijke conversieconclusies.

Een latere aanvullende dienst mag ondersteuning bieden bij meetplan, implementatie, consent,
tagging en handmatige validatie. De automatische basiscontrole en eerlijke betrouwbaarheidsstatus
blijven onderdeel van het product en worden niet afhankelijk gemaakt van die dienst.

## Verificatiekeuze voor de eerste release

Gebruik één willekeurig verificatietoken per website en ondersteun voor de eerste release een
bestand op een vaste HTTPS-locatie onder het geverifieerde domein. Sla alleen een hash van het token,
status, pogingen en tijdstippen op. Pas bestaande SSRF-, redirect-, timeout- en responslimieten toe.

Een DNS TXT-methode en HTML-metatag kunnen later als alternatieven worden toegevoegd. Bouw niet
direct drie methoden: één duidelijke, geteste methode is voldoende voor de besloten release.

## Benodigde implementatie

- Persistente onboardingstatus per organisatie of website met stappen, timestamps en laatste fout.
- Persistente websiteverificatie met tokenhash, status, pogingsteller en verificatietijd.
- API voor status, verificatie-instructie, verificatiecontrole en idempotent starten van de eerste
  crawl.
- Persistente analytics-onboardingstatus, meetdefinities met ingangsdatum, nulmeting,
  anomaliebewijs, hercontrolemomenten en confidence voor afhankelijke inzichten.
- Begeleide interface die alleen relevante velden toont en voortgang na herladen herstelt.
- Duidelijke foutafhandeling voor onbereikbaar verificatiebestand, verkeerd token, redirect buiten
  scope, actieve deployment-drain en mislukte eerste crawl.
- Automatische overgang naar crawlstatus en eerste resultaten zonder dat de gebruiker zelf door
  technische schermen hoeft te zoeken.
- Auditlogging voor uitnodiging, verificatie, eerste crawl en afronding.

Databasewijzigingen lopen via Alembic. Verstuur geen verificatietoken naar logs en start nooit meer
dan één initiële crawl voor dezelfde voltooide onboarding.

## Test- en acceptatiematrix

- Uitnodiging accepteren en opnieuw gebruiken weigeren.
- Onboarding hervatten na refresh en nieuwe login.
- Website en instellingen correct aanmaken binnen de eigen organisatie.
- Correct verificatiebestand accepteren; verkeerd of ontbrekend token duidelijk afwijzen.
- Redirects en private of lokale doelen opnieuw op SSRF-risico controleren.
- Dubbel klikken of opnieuw proberen maakt geen dubbele website of crawljob.
- Deployment-drain bewaart de onboardingstatus en laat later veilig hervatten.
- Eerste crawl toont pending, running, partially succeeded, succeeded en failed begrijpelijk.
- Een gebruiker van klant A kan onboarding en resultaten van klant B niet lezen of wijzigen.
- Zonder analyticskoppeling kan de technische onboarding worden afgerond zonder conversieclaims.
- Met analyticskoppeling worden conversie-inzichten pas betrouwbaar genoemd na een geslaagde
  meetkwaliteitscontrole.
- Een sterke event-/sessieafwijking krijgt status `aandacht nodig`, toont ruwe en gecorrigeerde
  gevoeligheidsuitkomst en blijft met bewijs en verificatiehistorie beschikbaar.
- Bij onvoldoende historie blijft de status voorlopig en worden hercontroles ingepland zonder de
  eerste crawl te blokkeren.
- Minimaal twee niet-technische proefgebruikers voltooien de flow zonder mondelinge technische
  instructies.

## Afbakening na deze release

Niet noodzakelijk voor friends-and-family:

- publieke zelfregistratie zonder uitnodiging;
- betaling of abonnementactivering;
- meerdere verificatiemethoden;
- automatische DNS-configuratie;
- uitgebreide producttour of marketingautomatisering.

## Bijgestelde raming

De bestaande basis voorkomt herbouw van authenticatie, rollen en crawlbeheer. Persistente
wizardstatus en eigendomsverificatie zijn echter nieuwe beveiligingsgevoelige onderdelen. Reken
daarom op 6–10 actieve werkdagen voor implementatie, tests, staging, productievalidatie en twee
gebruikersproeven. Herbereken na het definitieve verificatieontwerp en de eerste end-to-end test.
