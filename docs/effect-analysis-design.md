# Effectanalyse — kritisch ontwerpvoorstel

Status: ontwerpbesluit na Release 9; Fase A-fundering lokaal geïmplementeerd.

## Productdoel

Effectanalyse beantwoordt op cohortniveau welke KPI-ontwikkeling zichtbaar is na uitgevoerde
SEO-werkzaamheden. De module presenteert waarneming en bewijskracht, maar schrijft een ontwikkeling
niet automatisch causaal toe aan een wijziging.

De standaardvraag is:

> Welke ontwikkeling is zichtbaar voor de interventies die in deze periode zijn uitgevoerd?

Een individuele wijziging blijft inspecteerbaar, maar is niet de primaire rekeneenheid.

## Wat de codebase al heeft

- `changes` en `url_snapshots` bewaren gedetecteerde technische en inhoudelijke verschillen met
  voor- en nameting. Een generieke kopie als `seo_events` zou dezelfde feiten dupliceren.
- `issues`, occurrences en activiteitenhistorie bewaren signalen, bewijs en lifecycle.
- `recommendation_tasks` groeperen issues en URL's, hebben `implemented_at`, uitvoeringshistorie,
  verificaties en bevroren voor-/nasnapshots. Dit is de natuurlijke interventie-eenheid.
- GSC, Bing, GA4 en Matomo bewaren dagelijkse website- en waar beschikbaar paginametrics. De
  bewaartermijn van 1098 dagen maakt herberekening over ongeveer drie jaar mogelijk zonder live
  bronverzoek.
- URL's hebben een blijvende identiteit; verdwenen en omgeleide pagina's verliezen hun historie
  niet.
- Contentclassificaties zijn al append-only en versieerbaar via periode, inputhash,
  classificatieversie, confidence, brondekking en evidence. Een tweede classificatiehistorie is
  niet nodig.
- Opportunity-evaluaties hebben al formuleversie, deelscores, brondekking en evidence. Dezelfde
  begrippen moeten voor Effect worden hergebruikt, maar de opportunityscore zelf is geen
  effectscore.
- De analyticskwaliteitslaag voorkomt al dat onbetrouwbare GA4- of Matomo-data als harde conclusie
  wordt gebruikt en houdt providers strikt gescheiden.

## Gekozen richting

### 1. Taak als interventie

Een geïmplementeerde `RecommendationTask` is standaard één interventie. De gekoppelde URL's,
issues, taakcategorie, taaktype, events en verificaties vormen samen de scope en het bewijs. Wanneer
title, H1, tekst en interne links binnen één taak wijzigen, wordt KPI-ontwikkeling daardoor maar één
keer aan die interventie gekoppeld.

Automatisch gedetecteerde `changes` worden als ondersteunend bewijs aan de interventie gematcht op
URL en tijdvenster; ze worden niet gekopieerd. Een wijziging zonder taak kan later via een klein
handmatig interventierecord worden opgenomen. Bouw hiervoor niet vooraf een algemene eventbus.

### 2. Historische context bevriezen

Een effectevaluatie verwijst naar de gebruikte classificatierecords en bewaart daarnaast een klein
contextsnapshot met effectieve intentie, klantreisfase, contentrol en clusterlabel. Zo blijft een
oude uitkomst uitlegbaar als een classificatie of handmatige override later verandert, zonder een
tweede volledige classificatiehistorie te bouwen.

### 3. Metrics hergebruiken

Berekeningen lezen uitsluitend uit bestaande dagelijkse metriekentabellen. GSC en Bing blijven
afzonderlijke zoekbronnen; GA4 en Matomo blijven afzonderlijke analyticsproviders. De ingestelde
primaire analyticsbron bepaalt welke analyticsreeks wordt gebruikt. Ontbrekende dekking blijft
`unknown` en wordt nooit nul.

Query-URL-device-country-detail wordt pas toegevoegd als een concrete analysemethode dit nodig
heeft. Onbegrensde opslag op alle dimensies zou datavolume en API-kosten sterk verhogen zonder
bewezen productwaarde.

### 4. Evaluatie als versieerbaar resultaat

Een toekomstige `effect_evaluations`-tabel bewaart een herberekenbaar, immutable resultaat met
minimaal:

- website en cohort-/interventiescope;
- wijzigingsperiode, baselineperiode en observatieperiode;
- bron- en metricdefinities;
- methode- en formuleversie plus inputhash;
- gebruikte interventie-, URL-, classificatie- en metriekreferenties;
- brondekking, meetkwaliteitsstatus en alternatieve verklaringen;
- absolute en relatieve verschillen per KPI;
- volwassenheidsstatus en confidence;
- evidence en berekend tijdstip.

De unieke combinatie van scope, perioden, inputhash en methodeversie voorkomt duplicaten. Nieuwe
brondata of een betere methode maakt een nieuwe evaluatie en overschrijft de oude niet.

## Eerste analysemethode

De eerste versie gebruikt eenvoudige, controleerbare periodevergelijking:

1. Selecteer geïmplementeerde taken binnen de gekozen wijzigingsperiode.
2. Groepeer URL's per interventie en dedupliceer overlap binnen het cohort.
3. Kies gelijke baseline- en observatieperioden met voldoende afstand tot implementatie.
4. Aggregeer bestaande dagmetrics voor exact dezelfde URL-scope en bron.
5. Rapporteer verschillen, datadekking, meetkwaliteit, maturiteit en alternatieve verklaringen.

Zes weken wordt geen harde waarheid. De methode krijgt configureerbare observatievensters per brede
interventiecategorie, met als eerste veilige standaard 42 dagen. Uitkomsten kunnen zijn:
`too_early`, `insufficient_data`, `not_comparable`, `development_visible`,
`positive_indication`, `negative_indication` en `no_clear_effect`.

Seizoenscorrectie, controlegroepen, difference-in-differences en causale modellen volgen alleen als
voldoende datadichtheid en productbehoefte zijn aangetoond. De eerste versie vergelijkt waar
mogelijk ook dezelfde kalenderperiode een jaar eerder, maar blokkeert niet wanneer die ontbreekt.

## Confidence en formulering

Er komt geen tweede generieke confidence-engine en geen SEO-effectscore. Effectconfidence wordt
afgeleid uit dezelfde uitlegbare factoren als de bestaande analyses:

- bron- en scopedekking;
- meetkwaliteit;
- KPI-volume;
- vergelijkbaarheid van perioden;
- tijd sinds implementatie;
- overlap met andere interventies;
- aanwezigheid van verifieerbare crawlwijzigingen;
- bekende externe of meetkundige verstoringen.

De interface toont de factoren afzonderlijk. Toegestane conclusies lopen van `onvoldoende data` en
`te vroeg om te beoordelen` tot `sterke aanwijzing voor positieve ontwikkeling`. De tekst zegt
altijd dat samenhang geen bewezen causaliteit is.

## Belangrijkste risico's en begrenzing

- **Dubbele attributie:** overlappende taken en URL's worden binnen een cohort één keer geteld;
  detailweergaven verdelen dezelfde winst niet opnieuw over losse wijzigingen.
- **Selectiebias:** alleen uitgevoerde, geregistreerde taken zijn betrouwbaar analyseerbaar; dit
  wordt als dekking getoond.
- **Meetbreuken:** bronwissels, eventselectiewijzigingen, consentwijzigingen en
  meetkwaliteitsissues maken perioden mogelijk onvergelijkbaar.
- **Seizoen en externe invloeden:** algoritme-updates, campagnes, publicaties en marktvraag worden
  als alternatieve verklaring getoond wanneer bekend, niet stilzwijgend gecorrigeerd.
- **URL-mutaties:** blijvende URL-ID's, redirects en taakscope zijn leidend; stringmatching alleen is
  onvoldoende.
- **Datavolume:** bestaande dagaggregaten blijven de basis. Fijnmaziger dimensies worden gericht en
  met expliciete retentie toegevoegd.
- **Onderhoud:** methodeversies en immutable evaluaties voorkomen dat oude conclusies ongemerkt
  veranderen.

## Gefaseerde uitvoering

### Fase A — meetbare interventies

- Definieer task-to-intervention-regels en geldige implementatiemomenten.
- Leg contextsnapshot en verwijzingen vast zonder `changes` of metrics te kopiëren.
- Ondersteun eerst alleen geïmplementeerde taken met een concrete URL-scope.

Lokale uitwerking:

- `effect_interventions` bewaart per taak één immutable scope met implementatiemoment,
  taakdefinitie, URL-rollen en de historische effectieve contentclassificatie.
- Materialisatie is idempotent op taak en inputversie en weigert open of URL-loze taken.
- Materialisatie blijft voorlopig een expliciete serviceactie. Taakscope kan in de huidige workflow
  na `implemented` nog worden aangevuld; automatisch bevriezen tijdens die statusovergang zou
  daardoor onvolledige interventies kunnen vastleggen.
- Migration `0056` is additief en kopieert of herschrijft geen bestaande taak-, wijzigings- of
  metriekhistorie.

### Fase B — cohortberekening

- Voeg versieerbare effectevaluaties en één read-only berekenservice toe.
- Start met GSC en de ingestelde primaire analyticsbron.
- Implementeer maturiteit, dekking, overlapdetectie en conservatieve conclusies.

Lokale uitwerking:

- `effect_evaluations` bewaart immutable resultaten met inputhash en methodeversie.
- Methode 1 vergelijkt twee gelijke perioden van 28 dagen, hanteert 42 dagen maturiteit en vereist
  minimaal 14 dagen GSC-dekking per periode.
- Overlappende URL's worden binnen het cohort gededupliceerd en als confidencefactor geteld.
- GSC wordt gecombineerd met exact één ingestelde primaire analyticsbron: GA4 of Matomo.
- Per bron worden periode-, dekkings- en vergelijkbaarheidsgegevens expliciet opgeslagen.
- `development_visible` beschrijft alleen waargenomen samenhang; causaliteit wordt niet geclaimd.

### Fase C — interface en hercontrole

- Voeg een periodekeuze, cohortoverzicht, KPI-ontwikkeling en bewijsdetail toe.
- Laat berekenen een expliciete gebruikersactie blijven.
- Herbereken later gepland wanneer nieuwe brondata beschikbaar is; bewaar eerdere uitkomsten.

Lokale uitwerking:

- De Content-sectie bevat een afzonderlijke Effect-tab met expliciete berekenactie.
- De gebruiker kiest via de bestaande periodekeuze het interventiecohort; eerdere evaluaties blijven
  zichtbaar en worden niet bijgewerkt of verwijderd.
- Het overzicht toont status, basis- en observatieperiode, KPI-verschillen, brondekking, URL-aantal,
  overlap, methodeversie en de niet-causale bewijsnotitie.
- De tenantgebonden API ondersteunt uitsluitend expliciet berekenen en historische resultaten lezen.
- Een uitgevoerde taak kan vanuit het taakdetail expliciet en idempotent als immutable interventie
  worden vastgelegd; zonder URL-scope wordt dit geweigerd.
- Geplande automatische hercontrole blijft buiten deze fase; de immutable opslag ondersteunt dit
  later zonder bestaande uitkomsten te overschrijven.

### Later, alleen bij bewezen behoefte

- Handmatige interventies zonder taak.
- Vergelijkbare controlegroepen en seizoensmodellen.
- Effectgroepering over meerdere websites of klanten.
- Fijnmazige query-, device- en countrycohorten.
- Externe veranderingskalender en geavanceerde causale methoden.

## Besluit voor de eerstvolgende bouwfase

Bouw geen generieke `seo_events`-laag. Werk eerst Fase A uit op de bestaande taak-, URL-, change-,
classificatie- en verificatiehistorie. Maak vóór een migration een concreet veld- en queryontwerp en
toets dat met fixtures voor overlappende taken, URL-redirects, ontbrekende metrics en gewijzigde
classificaties.
