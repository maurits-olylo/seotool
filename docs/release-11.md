# Release 11 — Visuele issue-inspectie

Status: afgerond en geaccepteerd in staging en productie op 8 augustus 2026.

## Fase 1 — Uniform inspectiecontract

De eerste fase voegt een read-only inspectiecontract toe zonder nieuwe tabel, screenshotopslag of
browserwerk. `GET /api/v1/issues/{issue_id}/inspection` groepeert bestaande elementlocaties per
historische URL-snapshot en vermeldt expliciet:

- bron-URL, snapshot, crawlrun en meetmoment;
- of het bewijs bij de huidige issue-occurrence hoort;
- eventuele renderstatus en rendertijd;
- de best beschikbare locator met betrouwbaarheidsaanduiding;
- of het element gevonden of juist aantoonbaar afwezig is;
- dat live hercontrole in deze fase nog niet beschikbaar is.

Ontbrekende elementen krijgen nooit een kunstmatige selector. Issues zonder bruikbaar
elementbewijs blijven leesbaar met status `unavailable`, zodat de latere interface geen visuele
zekerheid suggereert die niet uit crawlbewijs volgt.

## Acceptatie fase 1

- Bestaande elementlocaties leveren `available` met een historische pagina en locator.
- Een ontbrekende H1 levert `limited` en een target van type `missing` zonder locator.
- De route gebruikt de bestaande websiteautorisatie en schrijft geen gegevens.
- Er is geen migration, nieuwe dependency, screenshotopslag of live browseraanroep.

## Fase 2 — Begrensde screenshotartefacten

Een succesvolle, expliciet ingeschakelde browserrender kan nu één PNG van de vaste viewport
`1365 × 768` bewaren. Volledige paginascreenshots zijn uitgesloten. Het artefact is maximaal 2 MB,
krijgt bestandsmodus `0600`, een SHA-256, grootte en vervaldatum en staat in een apart persistent
volume dat voor de API alleen-lezen is.

Migration `0058` voegt uitsluitend optionele metadata toe aan `render_observations`. De interne
opslagsleutel wordt niet via het inspectiecontract gepubliceerd. De API meldt alleen
beschikbaarheid, afmetingen en vervaldatum. Bij iedere nieuwe opslag worden maximaal honderd
artefacten ouder dan de ingestelde retentieperiode verwijderd; standaard is dat 90 dagen.

## Acceptatie fase 2

- Screenshotcapturing blijft onder dezelfde SSRF-, request-, timeout- en viewportgrenzen vallen.
- Een te grote PNG wordt niet opgeslagen en laat de inhoudsanalyse wel slagen.
- Opslag is atomair, privé en inhoudelijk gehasht.
- Productie en staging hebben elk een afzonderlijk persistent artefactvolume.
- Rendering blijft standaard uitgeschakeld.

## Fase 3 — Historische inspectie in het issuedetail

Het issuedetail toont nu het bestaande inspectiecontract als een aparte historische
inspectiesectie. Een bewaarde screenshot wordt uitsluitend via een tenant-geautoriseerde,
issuegebonden route geleverd; interne opslagsleutels blijven verborgen. De gebruiker ziet het
meetmoment, of dit de actuele issuewaarneming is en welke gevonden of ontbrekende elementen bij het
bewijs horen. Als geen screenshot of elementbewijs bestaat, blijft de technische bewijsroute
zichtbaar zonder een visuele locatie te suggereren.

Deze fase tekent nog geen elementoverlay in de afbeelding. Exacte geometrie wordt pas toegevoegd
wanneer de browserrender die betrouwbaar en viewportgebonden kan opslaan.

## Acceptatie fase 3

- Alleen een gebruiker met toegang tot de website kan het screenshotbestand ophalen.
- Verlopen, ontbrekende en onveilige artefactpaden leveren geen bestand op.
- De interface onderscheidt exact, beperkt en ontbrekend visueel bewijs.
- De screenshot is historisch gelabeld en wordt niet als live hercontrole gepresenteerd.

## Fase 4 — Betrouwbare elementmarkering

De browserrender bewaart naast de vaste viewport-screenshot maximaal vijfhonderd zichtbare
elementgeometrieën in de bestaande comparison-metadata. De inspectieservice koppelt een issue alleen
aan een kader bij één eenduidige ID-match of één exacte combinatie van elementtype, doel, tekst en
volgnummer. Dubbele, ongeldige of ontbrekende matches leveren bewust geen overlay op.

## Acceptatie fase 4

- Geometrie is gebonden aan dezelfde vaste viewport als de screenshot.
- Alleen positieve, eenduidig gekoppelde rechthoeken worden gepubliceerd.
- De interface schaalt het kader mee met de responsieve screenshot.
- Oude screenshots zonder geometrie blijven zonder fout en zonder kunstmatige markering werken.

## Fase 5 — Expliciete live hercontrole

Een beheerder kan vanuit het issuedetail één expliciete live hercontrole starten. De controle
gebruikt de bestaande beveiligde renderqueue en blijft achter dezelfde standaard uitgeschakelde
rendering-featureflag. Tijdens de hercontrole blijft het historische screenshot zichtbaar; de
interface toont daarnaast de actuele wachtrij- of uitvoerstatus en ververst het resultaat
automatisch.

Een live hercontrole wordt als afzonderlijke renderwaarneming opgeslagen. Daardoor overschrijft
een nieuwe meting het oorspronkelijke crawlbewijs niet. Een rijvergrendeling en hergebruik van een
al actieve waarneming voorkomen dat dubbel klikken meerdere gelijktijdige controles voor dezelfde
snapshot start. De start wordt als security-event vastgelegd.

## Acceptatie fase 5

- Alleen een beheerder met toegang tot de website kan een live hercontrole starten.
- Zonder ingeschakelde rendering of inspecteerbare snapshot wordt geen taak aangemaakt.
- Herhaald starten tijdens een lopende controle levert dezelfde renderwaarneming op.
- Historisch bewijs blijft beschikbaar terwijl de nieuwe controle wacht of draait.
- De interface onderscheidt crawlbewijs van een live hercontrole en meldt slagen of mislukken.
- Er ontstaan geen automatische browseraanroepen; rendering blijft standaard uitgeschakeld.

## Fase 6 — Gerichte live inspectie

Een live hercontrole gebruikt het eerste betrouwbaar gelokaliseerde issue-element als optioneel
focusdoel. De renderworker zoekt dit doel na het laden in de actuele DOM, accepteert alleen een
unieke match en scrolt het element naar het midden van de vaste viewport voordat geometrie en
screenshot worden vastgelegd. De bestaande overlay kan het probleem daardoor ook aanwijzen wanneer
het buiten de oorspronkelijke eerste viewport stond.

De focusopdracht bevat alleen een begrensde ID-, CSS- of unieke tekstlocator uit opgeslagen
crawlbewijs. Een ontbrekend element, onbetrouwbare XPath of niet-unieke actuele match leidt nooit
tot geforceerd scrollen. De live controle blijft dan als gewone viewportwaarneming bruikbaar.

## Acceptatie fase 6

- Alleen een opgeslagen betrouwbare locator kan als focusdoel naar de renderworker gaan.
- De actuele DOM moet exact één match bevatten voordat de pagina scrolt.
- Elementgeometrie en screenshot worden pas na een geslaagde focuspoging vastgelegd.
- Een ongeldig, verdwenen of dubbel element breekt de render niet en levert geen kunstmatige focus.
- Reguliere renderwaarnemingen zonder issuefocus behouden hun bestaande gedrag.

## Fase 7 — Schaalbare inspectie van meerdere bronpagina's

Issues met bewijs op meerdere bronpagina's laden in het issuedetail nog maar één geselecteerde
paginaweergave tegelijk. Een compacte paginakeuze toont URL en positie binnen de bewijsset. De
actuele issuewaarneming is de standaardselectie; tijdens verversen blijft de handmatig gekozen
snapshot behouden zolang die nog beschikbaar is.

De live-hercontroleroute accepteert optioneel de geselecteerde snapshot. De server controleert dat
de snapshot werkelijk bij de inspectie van dit issue hoort voordat een renderwaarneming wordt
aangemaakt. Daardoor kan een gebruiker gericht één bronpagina controleren zonder stilzwijgend de
eerste URL of een willekeurige andere tenantpagina te laten renderen.

## Acceptatie fase 7

- Bij meerdere bronpagina's wordt slechts één screenshot tegelijk in de interface geladen.
- De selector toont de bron-URL en de positie binnen de volledige bewijsset.
- Een gekozen pagina blijft geselecteerd tijdens statusverversing en live polling.
- Live hercontrole gebruikt exact de geselecteerde snapshot.
- Een onbekende of niet bij het issue horende snapshot wordt geweigerd zonder taak aan te maken.
- Op 390 px staat de paginakeuze onder elkaar zonder horizontale overflow.

## Fase 8 — Eenduidige live elementuitkomst

Een voltooide live hercontrole vermeldt nu afzonderlijk of het historische doelelement in de
actuele DOM exact één keer is gevonden, niet is gevonden, meerdere keren voorkomt of niet
betrouwbaar kon worden vastgesteld. Alleen een unieke match wordt naar de viewport gescrold en kan
een live overlay krijgen. De interface toont de uitkomst naast het meetmoment en blijft het
historische elementbewijs als zodanig presenteren.

Deze uitkomst is inspectiebewijs en geen automatische issuebeslissing. Een niet gevonden element
kan betekenen dat een defecte link of CTA is verwijderd, maar ook dat pagina-opmaak is gewijzigd.
Oplossen en verifiëren blijven daarom via de bestaande taak-, crawl- en issue-lifecycle lopen.

## Acceptatie fase 8

- Een unieke actuele DOM-match wordt als `found` gepubliceerd en visueel bevestigd.
- Nul matches, meerdere matches en technische onzekerheid krijgen verschillende uitkomsten.
- Een historische of nog lopende observatie meldt nooit ten onrechte een live uitkomst.
- Alleen `found` geldt als geslaagde focus; overige uitkomsten krijgen geen kunstmatig kader.
- De interface gebruikt begrijpelijke Nederlandse labels en verandert de issue-status niet.

## Fase 9 — Live controle van ontbrekende elementen

Voor historische issues over een ontbrekende H1, title, meta description of BreadcrumbList bewaart
de live renderopdracht nu een begrensde afwezigheidscontrole. Na rendering controleert de bestaande
HTML-extractie of het element in de actuele pagina nog ontbreekt of inmiddels aanwezig is. Daarvoor
wordt geen selector verzonnen en geen extra browseraanroep uitgevoerd.

De interface toont `Element ontbreekt live nog` of `Element is live aanwezig`. Een aanwezig element
is een sterk herstelsignaal, maar geen formele verificatie: de gewone crawler moet het issue via de
bestaande lifecycle oplossen en bij de volgende geslaagde controle verifiëren.

## Acceptatie fase 9

- Alleen ondersteunde ontbrekende-elementtypen krijgen een live afwezigheidscontrole.
- H1, title, meta description en BreadcrumbList gebruiken de bestaande renderextractie.
- Een live aanwezig element wordt onderscheiden van een nog steeds ontbrekend element.
- Ontbrekende elementen krijgen nooit een kunstmatige locator of overlay.
- De controle start geen extra netwerkverzoek en verandert de issue-status niet.

## Fase 10 — Integrale lokale releaseacceptatie

De volledige applicatiesuite, linting, JavaScript-syntaxis, productie- en staging-Compose,
migrationketen en OpenAPI-routes zijn gezamenlijk gecontroleerd. Zowel productie als staging heeft
een aparte, alleen via het profiel `rendering` actieve volume-initialisatie. Die zet uitsluitend de
root van het screenshotvolume op gebruiker `pwuser` en modus `0700` voordat de niet-root
renderworker start. Dit werkt ook wanneer Compose het named volume al eerder root-owned aanmaakte.
De initialisatietaak houdt `cap_drop: ALL` en krijgt uitsluitend `CHOWN` en `FOWNER` terug voor deze
ene volumebewerking; netwerktoegang en overige Linux-capabilities blijven uitgesloten.

Migration `0060` verwijdert alleen de unieke constraint op `source_snapshot_id`; er is geen
dataherschrijving. Voor staging is daarom geen extra databaseback-up nodig. Voor productie wordt
wel de normale pre-deploymentback-up gebruikt, omdat een schemadowngrade na meerdere live
observaties niet meer zonder een expliciete datakeuze kan worden uitgevoerd. Een applicatierollback
mag de database in dat geval veilig op `0060` laten staan.

## Acceptatie fase 10

- Productie- en staging-Compose zijn geldig met en zonder het renderingprofiel.
- De renderworker start pas nadat het artefactvolume bruikbaar is voor `pwuser`.
- API houdt read-only toegang; alleen de renderworker schrijft screenshots.
- Crawler- en API-databaserollen hebben de benodigde bestaande tabelrechten.
- Alembic heeft exact één head: `0060`.
- Inspectie-, hercontrole- en screenshotroutes staan in OpenAPI.
- Rendering en de renderworker blijven standaard uitgeschakeld.

## Stagingacceptatiefixture

Staging bevat één synthetische renderpagina op `/staging/render-acceptance`. De pagina bevat geen
klantdata en begint zonder H1. Een geautoriseerde technische aanvraag kan de pagina omschakelen
naar een herstelde toestand met exact één H1. Productie en alle andere omgevingen geven voor beide
routes `404`.

De renderworker mag uitsluitend in `APP_ENV=staging` de exacte interne URL van deze pagina openen.
Andere interne URL's blijven onder de bestaande SSRF-blokkade vallen. Hierdoor kunnen historische
screenshotopslag en de live uitkomst `Element is live aanwezig` end-to-end worden geaccepteerd,
zonder externe website, productie-integratie of klantcrawl.

De fixture is de eerste ingang in de herbruikbare acceptatiecatalogus uit
`docs/acceptance-roadmap.md`. Nieuwe scenario's krijgen later een eigen vaste ID en exacte
staging-URL; de renderer krijgt nooit een algemene uitzondering voor interne adressen.

## Eindacceptatie staging

- Releasecommit `358aa1b` is via het vaste Git-archive en de interactieve NAS-route gedeployed.
- API, PostgreSQL, Redis en renderworker waren gezond op migration-head `0060`.
- De synthetische fixture maakte uitsluitend het bedoelde actieve `missing_h1`-issue aan; een
  eerdere fout-positieve `javascript_metadata_conflict` is geverifieerd en de regressie is afgedekt.
- De historische inspectie behield de screenshot en meldde `Element ontbreekt`.
- De expliciete live hercontrole eindigde met `Element is live aanwezig`, zonder de historische
  waarneming te overschrijven.
- De browser rapporteerde geen fouten of waarschuwingen.

## Eindacceptatie productie

- Voor migraties `0058` tot en met `0060` is de bestaande versleutelde productieback-up volledig
  aangemaakt en gecontroleerd.
- API, integration-worker, renderworker, PostgreSQL en Redis waren na herstart gezond.
- De database rapporteerde exact één head: `0060`.
- Rendering was actief voor API en renderworker; de renderworker was geregistreerd en kon naar het
  afzonderlijke artefactvolume schrijven.
- Inspectie- en hercontroleroutes stonden in OpenAPI en de publieke healthcheck meldde database en
  API gezond.
- De crawl-drain is na alle controles veilig hervat zonder wachtende taken te hervatten.
- De productie-interface laadde bestaande klantdata en een bestaand `missing_h1`-issue toonde
  historische inspectie, beperkt bewijs, ontbrekend element en de knop voor live hercontrole.
- Er is tijdens productieacceptatie bewust geen live render van een klantpagina gestart; de
  muterende end-to-end-flow was al met synthetische stagingdata bewezen.
- De browser rapporteerde geen fouten of waarschuwingen.

## Operationele leerpunten

- Wanneer een environmentbestand de regel `RENDERING_ENABLED` nog niet bevat, kan een vervangende
  `sed`-opdracht niets wijzigen. Controleer vóór toekomstige releases of de sleutel bestaat en voeg
  haar gecontroleerd toe wanneer zij ontbreekt.
- Houd lange NAS-ketens binnen een praktisch kopieerbare lengte. Een blijvende `>`-prompt betekent
  dat de shell op ontbrekende invoer wacht en dat de keten nog niet is uitgevoerd.
- Ga na een migratie, deployment of correctie uit van een verbroken stagingtunnel en open die vóór
  browseracceptatie opnieuw.
