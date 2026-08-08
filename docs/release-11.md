# Release 11 — Visuele issue-inspectie

Status: fasen 1 tot en met 6 lokaal geïmplementeerd; nog niet gedeployed.

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
