# Release 11 — Visuele issue-inspectie

Status: fasen 1 en 2 lokaal geïmplementeerd; nog niet gedeployed.

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
