# Release 11 — Visuele issue-inspectie

Status: fase 1 lokaal geïmplementeerd; nog niet gedeployed.

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
