# Continuous Website Improvement — architectuuranalyse en ontwerp

Status: ontwerpbesluit, nog geen implementatie  
Datum: 8 augustus 2026

## 1. Executive summary

De voorgestelde verbreding past bij Thactual, mits het product niet wordt omgebouwd tot een
generiek platform voordat daar concrete gebruikssituaties voor bestaan. De huidige code ondersteunt
de kerncyclus al:

`signaal → issue → aanbevelingstaak → verificatie → interventie → effect → historie`.

Accessibility is een geschikte tweede kwaliteitsbron omdat zij de bestaande render-, element-,
issue-, taak- en verificatiearchitectuur kan hergebruiken. De eerste versie moet daarom geen aparte
WCAG-app, score of certificeringsmodule worden. Zij moet een kleine set betrouwbare automatische
bevindingen normaliseren naar gewone Thactual-issues en herhaalde bevindingen bundelen tot één
uitvoerbare component- of templateactie.

De belangrijkste ontbrekende bouwsteen is niet een universeel `problem`-model. Nodig is eerst een
kleine, expliciete relatie waarmee één verbetering meerdere issues en bewijsdomeinen kan dragen.
`recommendation_task_issues` ondersteunt dit relationeel al; creatie, bundeling en presentatie
gebruiken het nog onvoldoende.

Aanbevolen volgorde:

1. accessibility-pilot op de bestaande renderworker;
2. betrouwbare normalisatie, historie en componentgroepering;
3. meerdere issues naar één taak met uitlegbare prioriteitsfactoren;
4. pas daarna enkele cross-domain kansen en testkandidaten;
5. informatiearchitectuur verder verschuiven naar Inzichten, Kansen en Acties wanneer de inhoud dat
   werkelijk draagt.

## 2. Huidige product- en architectuurpositie

Thactual is technisch al meer dan een SEO-monitor. De gegevensstroom bestaat uit blijvende
URL-identiteit, historische snapshots, wijzigingen, issues en bewijs, analytics- en zoekdata,
contentclassificatie, kansen, uitvoeringstaken, gerichte verificatie, interventies en effectmeting.

De architectuur is per bron en uitvoering gescheiden:

- PostgreSQL bewaart blijvende toestand en historie;
- Redis/RQ voert crawl-, integratie-, verificatie-, rendering-, onderhouds- en exportwerk uit;
- gewone HTTP-crawls blijven primair;
- browserwaarnemingen staan apart van statische snapshots;
- API-autorisatie begrenst toegang per gebruiker, klant en website;
- de interface bevat al Acties, Inzichten en binnen Content aparte Kansen en Effect.

De producttaal en enkele modellen zijn nog SEO-gecentreerd, maar de technische kern is grotendeels
domeinonafhankelijk.

## 3. Reeds aanwezige bouwstenen

| Bouwsteen | Bestaande implementatie | Hergebruik |
|---|---|---|
| URL-identiteit en historie | `Url`, `UrlSnapshot`, `Change` | ongewijzigd gebruiken |
| Elementbewijs | `ElementLocation`, selectors, context, rendergeometrie | WCAG-nodebewijs opslaan en inspecteren |
| Signaallifecycle | `Issue`, `IssueOccurrence`, `reconcile_issues` | accessibility-issues dedupliceren en heropenen |
| Groepering | template- en shared-resourceanalyse | uitbreiden met DOM-/componenthandtekening |
| Taken | `RecommendationTask`, `RecommendationTaskIssue`, URL-scope | één taak uit meerdere bevindingen |
| Persona's | versiebeheer in recommendation library en taakrollen | `ux_ui_design`, `web_development`, `content_editor` |
| Verificatie | `RecommendationVerification`, gerichte executor | accessibility-hercontrole als nieuw verificatietype |
| Interventie | `EffectIntervention` met taaksnapshot | wijziging historisch vastleggen |
| Effect | `EffectEvaluation`, analyticsdekking en confidence | later cross-domain resultaatcontext toevoegen |
| Kansen | `OpportunityEvaluation`, contributors, evidence, shared cause | geen nieuw opportunity-model maken |
| Contentcontext | intent, journey stage, content role, overrides | testbaarheid en journey-frictie duiden |
| Analytics | GSC, GA4, Matomo en Bing, per URL gekoppeld | businesscontext en bereik onderbouwen |
| Rendering | Playwright, SSRF-beveiliging, screenshots, live inspectie | axe binnen dezelfde begrensde paginasessie uitvoeren |
| Operations | queues, admission control, retries, dead letters, retentie | accessibility als eigen begrensde queue/beleid |

## 4. Fit met continuous website improvement

De verbetercyclus is aanwezig, maar verspreid over drie productlagen:

- issues beschrijven automatisch gemeten diagnoses;
- recommendation tasks beschrijven menselijke uitvoering en verificatie;
- interventions/effects bewaren de wijziging en latere ontwikkeling.

Daarmee is geen fundamentele herbouw nodig. De belangrijkste productverbetering is de cyclus als één
doorlopend verhaal presenteren. Een gebruiker moet van bewijs naar gedeelde verbetering, uitvoering,
controle en resultaat kunnen gaan zonder de onderliggende engines te hoeven begrijpen.

## 5. Belangrijkste risico's en scope creep

- Een generiek finding/problem/opportunity/intervention-framework zou bestaande goede modellen
  dupliceren.
- Een universele score maakt prioriteit ondoorzichtig en botst met het bestaande bewijsmodel.
- Een WCAG-dashboard per engine zou de gebruiker opnieuw zelf laten prioriteren.
- Iedere URL renderen op iedere crawl overschrijdt de huidige NAS-capaciteit.
- Automatische bevindingen presenteren als conformiteitsbewijs creëert juridisch en productmatig
  schijnzekerheid.
- Inzichten/Kansen/Acties direct als volledige navigatierewrite uitvoeren is te vroeg: Kansen en
  Effect bestaan nu vooral binnen Content en hebben nog onvoldoende domeinbrede inhoud.

## 6. Accessibility/WCAG-fit

Accessibility past goed omdat het dezelfde eenheden gebruikt als bestaande SEO-controles:

- URL en historisch meetmoment;
- concreet element of aantoonbare afwezigheid;
- technische regel en bewijs;
- confidence en reviewbehoefte;
- herhaling op templates/components;
- taak, eigenaar en verificatie;
- opgelost, teruggekomen of regressie.

De productclaim blijft: automatische WCAG-monitoring en ondersteunde beoordeling. Niet: volledige
WCAG 2.2 AA-conformiteit.

## 7. axe-core versus alternatieven

axe-core is de aanbevolen eerste engine. De engine ondersteunt WCAG 2.0, 2.1 en 2.2, levert
regelmetadata en tags, onderscheidt violations van incomplete resultaten en kan rechtstreeks in een
bestaande browsersessie worden uitgevoerd. Deque meldt zelf dat automatische tests gemiddeld maar
een deel van de WCAG-problemen vinden en dat incomplete resultaten menselijke beoordeling vragen.
Zie de officiële [axe-core repository](https://github.com/dequelabs/axe-core) en
[API-documentatie](https://github.com/dequelabs/axe-core/blob/develop/doc/API.md).

Alternatieven zijn nu minder passend:

- Lighthouse accessibility hergebruikt deels axe maar geeft minder controle over normalisatie en
  bewijs;
- Pa11y is vooral orchestration rond engines en voegt naast de bestaande worker weinig toe;
- een eigen engine is onnodig, kostbaar en risicovol;
- commerciële auditplatforms kunnen later een provider zijn, maar mogen het domeinmodel niet bepalen.

Technisch verdient een vast gepinde `axe-core`-versie in het renderimage de voorkeur. De worker
injecteert de lokale distributie in de bestaande pagina; geen CDN of extra extern verzoek.

## 8. Aanbevolen accessibilityarchitectuur

Eerste gegevensstroom:

`renderselectie → bestaande beveiligde browsersessie → axe.run → begrensde raw result → normalisatie
→ issue occurrences → componentgroepering → taak → gerichte rerender-verificatie`.

Bewaar niet de volledige axe-response. Bewaar per genormaliseerde bevinding:

- engine en gepinde versie;
- externe rule ID;
- eigen stabiele `issue_type`;
- WCAG-versie, criterium en niveau;
- automatic/review-classificatie;
- impact en Thactual-severity afzonderlijk;
- begrensde selectors, HTML-fragmenten en failure summary;
- URL, snapshot, renderwaarneming en meetmoment;
- componenthandtekening en aantal getroffen pagina's;
- relevante datadekking.

## 9. Automatic, semi-automatic en manual

Gebruik drie verificatieklassen:

- `automatic`: een failure is technisch betrouwbaar en dezelfde regel kan herstel automatisch
  vaststellen;
- `review_required`: engine levert verdachte/incomplete evidence of betekenis moet worden beoordeeld;
- `manual`: Thactual biedt instructie, sample, reviewer en bewijs, maar doet geen automatische claim.

Deze classificatie hoort bij de eigen rule mapping, niet rechtstreeks bij de toevallige engine-output.
De bestaande `confidence`, issue-status `review` en verificatie-uitkomst `manual_review` zijn hiervoor
bruikbaar. Een uitgebreide auditworkflow volgt pas na de automatische pilot.

## 10. WCAG mapping en versioning

Voeg in de pilot geen volledige normcatalogus in tabellen toe. Begin met een versieerbaar
codebestand, vergelijkbaar met de recommendation library:

- interne rule key en mappingversion;
- engine rule ID en ondersteunde engineversies;
- WCAG 2.2-criteria en niveau;
- verification class;
- titel, uitleg, rol, actie en gereedcriterium.

Een databasecatalogus wordt pas nodig wanneer handmatige audits, meerdere engines of beheerbare
normversies werkelijk worden gebouwd.

## 11. Normalisatie naar bestaande issues

Accessibility-findings worden gewone issues met `category="accessibility"`. Voeg niet meteen een
algemeen `domain`-veld aan alle issues toe. De bestaande centrale classificatielaag kan issue type
naar één of meer presentatiedomeinen mappen, zoals `accessibility`, `seo` en `ux`.

De huidige unieke sleutel `(website_id, url_id, issue_type)` is voldoende voor URL-bevindingen.
Componentclusters blijven sitebrede issues met `url_id=NULL`, zoals bestaande templateclusters.

## 12. Component- en templategroepering

Begin deterministisch. Maak een componenthandtekening uit:

- interne issue type;
- gestabiliseerde selector/DOM-route;
- elementtype, rol en toegankelijke-naamstatus;
- begrensde HTML-structuur zonder dynamische IDs/waarden;
- bestaande URL-familie of paginatype.

Bundel pas bij minimaal twee URL's en toon sample-URL's, bereik en confidence. Noem het een
`waarschijnlijke gedeelde component` zolang geen broncodecomponent bekend is. Bouw geen algemene
dependency graph.

## 13. Cross-domain finding model

Maak nu geen nieuw raw-findingmodel. Gebruik:

- `IssueOccurrence.evidence` voor bronbewijs;
- issue-typeclassificatie voor één of meer domeinen;
- `RecommendationTaskIssue` voor meerdere diagnoses achter één verbetering;
- `OpportunityEvaluation.contributors` voor context en prioriteitsfactoren.

Pas wanneer minstens twee nieuwe engines dezelfde normalisatiebehoefte hebben, is een afzonderlijke
persistente `finding`-laag gerechtvaardigd.

## 14. Cross-domain prioritering

Behoud de bestaande berekening als hulpmiddel, maar presenteer factoren in plaats van alleen een
totaalscore:

- impactdomeinen;
- bereik: pagina, URL-familie, component of sitebreed;
- confidence en ontbrekende bronnen;
- effort en feasibility;
- urgentie/regressie;
- businesscontext: verkeer, conversies, journey-rol, belangrijke URL;
- eerdere uitkomst, later en uitsluitend binnen passende context.

Voorbeeld: `Hoge prioriteit: lage inspanning, accessibility- en SEO-impact op 428 belangrijke
pagina's.` De score blijft intern sorteerbaar; de uitleg is leidend.

## 15. Problem, opportunity, intervention en task

Huidige modellen zijn voorlopig voldoende:

- issue = gemeten probleem/signaal;
- opportunity evaluation = onderbouwde kans of monitorbesluit;
- recommendation task = gekozen verbetering/actie;
- effect intervention = werkelijk uitgevoerde wijziging;
- effect evaluation = ontwikkeling na die wijziging.

Voeg geen los `problem`-object toe. Verbeter eerst multi-issue taakcreatie en shared-cause grouping.

## 16. Testing candidates

Een testkandidaat is een opportunity, geen issue. Eerste deterministische types:

- sterke SEO-prestatie plus commerciële rol plus lage conversie;
- veel relevante landingssessies plus lage logische doorstroom;
- voldoende mobiel volume plus materieel slechtere mobiele uitkomst;
- hoog bereik plus concrete CTA-/accessibilityfrictie.

De output is `experiment overwegen`, nooit `probleem bewezen`.

## 17. Testability

Gebruik aanvankelijk drie banden: `testable`, `longer_observation_needed` en
`effect_measurement_preferred`. Baseer dit op beschikbaar verkeer en relevante events, maar leg geen
universele statistische drempels vast voordat echte klantdata is onderzocht. Bouw geen A/B-delivery
of significantieplatform.

## 18. Journey-friction intelligence

Dit is het beste vroege cross-domain opportunitytype omdat `analytics_journey`, contentrollen,
journey stages, GA4 en Matomo al bestaan. Vereist zijn voldoende instroom, een verwachte volgende
fase en meetbare downstream interactie. Bounce rate alleen is nooit bewijs.

## 19. Andere waardevolle combinaties

Pareto-volgorde:

1. belangrijk URL + technisch/accessibilityprobleem;
2. gedeelde component + meerdere issues + groot bereik;
3. veel verkeer + commerciële rol + lage doorstroom;
4. transactionele query + informatieve pagina + zwakke doorstroom;
5. mobiele vraag + mobiele performance/accessibility + slechtere uitkomst;
6. contentveroudering + dalende vraag + businessbelang;
7. technische wijziging + nieuwe regressie.

## 20. Tegenstrijdige signalen en geen actie

Gebruik `priority_class="monitor"` en `insufficient_evidence` al als basis voor geen directe actie.
Voeg eerst duidelijke redenen toe aan contributors/evidence. Een apart persistent `no_action`-model
is niet nodig. De interface moet kunnen zeggen dat een afwijking is beoordeeld maar nu geen wijziging
rechtvaardigt.

## 21. Inzichten, Kansen en Acties

De richting klopt, maar voer haar incrementeel uit:

- Inzichten: betekenisvolle observaties, inclusief geen-actie-uitkomsten;
- Kansen: onderbouwde verbeteropties en testkandidaten;
- Acties: menselijke uitvoering, controle en resultaat.

Content, Accessibility, SEO en Performance blijven filters en bewijsbronnen. Accessibility krijgt
in de eerste pilot geen eigen primaire dashboardtab.

## 22. Domeinen als filters en evidence

Introduceer een centrale, codegedreven mapping van issue-/opportunitytype naar een set domeinen.
Hiermee kan één item `SEO + Accessibility` tonen zonder de bestaande `category`-semantiek of alle
historische rijen te migreren. Maak pas een relationele domeintabel wanneer gebruikers domeinen zelf
kunnen configureren.

## 23. Persona- en workflowintegratie

De bestaande taakrollen zijn voldoende. Mappingvoorbeelden:

- ARIA/component: `web_development`, ondersteunend `ux_ui_design`;
- alt-tekstinhoud: `content_editor`, bij componentprobleem `web_development`;
- focus/interaction review: `ux_ui_design`;
- auditcoördinatie: `website_management`.

De uitvoerder ziet één actie; specialistische criteria en enginebewijs staan in de detailweergave.

## 24. Verification

Voeg één gerichte `accessibility_rule_recheck` toe die exact de taak-URL's of representatieve samples
rendert en alleen gekoppelde regels uitvoert. Automatische pass kan een taakverificatie laten slagen;
review-required blijft `manual_review`. Een volgende brede scan bepaalt regressie en issue-lifecycle.

## 25. History en regressie

`first_detected_at`, occurrences, resolved/verified en heropening leveren de basis. Voeg in de
presentatielaag `recurring` en `regression` afgeleid toe wanneer een geverifieerd issue later opnieuw
verschijnt. Bewaar aantallen per componentcluster per scan om groei en krimp te tonen.

## 26. Relatie met Effect

Accessibilitytaken gebruiken dezelfde interventieregistratie. Effect hoeft niet altijd analytics te
betekenen: de eerste uitkomst kan technisch zijn, bijvoorbeeld aantal getroffen pagina's van 842
naar 0. Houd technische verificatie en gedrags-/zoekeffect gescheiden in de uitleg.

## 27. Historical learning

De huidige task snapshot, feedback, verification result en effect evidence bewaren voldoende basis.
Bouw nog geen lerend prioriteitsmodel. Begin later met sitegebonden beschrijvende patronen, zoals
`vergelijkbare componentfixes slaagden 4 van 5 keer`, met minimumvolume en zonder causaliteitsclaim.

## 28. Performance-, worker- en crawlimpact

Voer axe uit in dezelfde renderpagina vóór contextsluiting. Daarmee vervallen een tweede navigatie en
extra netwerkverzoeken. Wel nemen CPU- en evaluatietijd toe. Gebruik daarom:

- een eigen accessibility-queue of expliciete queuepolicy;
- concurrency één op de NAS;
- maximaal aantal nodes/findings en begrensde evidence;
- baseline op representatieve templates en belangrijke pagina's;
- daarna gewijzigde URL's, periodieke sample en gerichte verificatie;
- afzonderlijke metingen van render-, axe- en opslagtijd.

De eerste pilot mag niet automatisch aan iedere volledige crawl worden toegevoegd.

## 29. Pareto-versie

De eerste bruikbare versie bevat:

- axe-core met een gepinde versie;
- circa 8–12 betrouwbare regels uit forms, names/roles, language en structure;
- violations en incomplete strikt gescheiden;
- normalisatie naar bestaande issues;
- elementbewijs en historische inspectie;
- groepering op gedeelde componenthandtekening;
- één taak uit meerdere gekoppelde issues;
- gerichte automatische hercontrole;
- regressie-indicatie;
- geen conformiteitsscore of auditverklaring.

## 30. Concrete roadmapplaats

Release 11 levert de technische prerequisite: volwaardige visuele inspectie en repeatable rendering.
De volgende substantiële productrelease moet echter niet direct accessibility breed uitrollen.

Aanbevolen plaats:

1. eerst de bestaande privacy- en securitygates respecteren;
2. daarna een kleine accessibility foundation/pilot als eerste cross-domain testcase;
3. vervolgens multi-issue/shared-cause prioritering;
4. daarna journey-friction en testkandidaten;
5. pas met voldoende inhoud de navigatie volledig naar Inzichten/Kansen/Acties verschuiven.

## 31. Fasering

### Fase A — afgerond met dit document

Architectuurfit, hergebruik, risico's en roadmapplaats vastgesteld.

### Fase B — accessibility pilot

Engine-integratie, mappingcatalogus, genormaliseerde opslag, kleine selectie, bewijs en tests.

### Fase C — grouping en workflow

Componenthandtekening, bereik, multi-issue taak, gerichte verificatie en regressie.

### Fase D — cross-domain prioritization

Uitlegbare factoren, businesscontext en één verbetering uit meerdere domeinen.

### Fase E — opportunities en testability

Journey-frictie, underperforming winners, intent mismatch en device friction.

### Fase F — informatiearchitectuur en leren

Productbrede Inzichten/Kansen/Acties en later beschrijvend historisch leren.

## 32. Bewust niet bouwen

- WCAG-certificering of complianceverklaring;
- accessibilityscore of universele kwaliteitsscore;
- eigen accessibility-engine;
- volledige handmatige auditworkflow in de pilot;
- universele rules engine;
- generiek problem- of findingmodel;
- A/B-testdelivery en statistisch experimentplatform;
- automatische causaliteitsclaims;
- afzonderlijke dashboards per discipline;
- klantoverstijgend leren met ruwe klantdata.

## 33. Benodigde minimale refactors

1. Maak multi-issue taakcreatie een ondersteunde serviceoperatie in plaats van alleen een bestaand
   relationeel datamodel.
2. Centraliseer meervoudige domeinlabels per issue-/opportunitytype zonder historische migratie.
3. Laat renderuitvoering optionele, begrensde evaluators uitvoeren en timing/resultaat teruggeven.
4. Maak componenthandtekening en grouping een kleine gedeelde utility voor rendering-, performance-
   en accessibilitysignalen.

Niet aanpassen: URL-register, snapshotmodel, issue-lifecycle, taakstatussen, verificatiescheiding,
interventies, effectevaluaties, autorisatiemodel en queue-admission.

## 34. Relevante bestaande bestanden en modules

- `app/models/issues.py`
- `app/models/recommendations.py`
- `app/models/opportunities.py`
- `app/models/effects.py`
- `app/models/crawl.py`
- `app/models/rendering.py`
- `app/services/issue_engine.py`
- `app/services/template_issue_analysis.py`
- `app/services/opportunity_engine.py`
- `app/services/opportunity_scoring.py`
- `app/services/recommendation_tasks.py`
- `app/services/recommendation_verifications.py`
- `app/services/effect_interventions.py`
- `app/services/effect_analysis.py`
- `app/services/browser_renderer.py`
- `app/services/render_executor.py`
- `app/services/analytics_journey.py`
- `app/services/content_intent_insights.py`
- `app/core/queue.py`
- `app/services/authorization.py`
- `app/ui/index.html`
- `app/ui/app.js`

## 35. Waarschijnlijke nieuwe bestanden

Eerste pilot, namen indicatief:

- `app/services/accessibility/rule_catalog.py`
- `app/services/accessibility/normalization.py`
- `app/services/accessibility/grouping.py`
- `app/services/accessibility/analysis.py`
- `app/schemas/accessibility.py`
- `tests/fixtures/accessibility/*.html`
- `tests/test_accessibility_normalization.py`
- `tests/test_accessibility_grouping.py`
- `tests/test_accessibility_verification.py`

Een nieuw databasemodel is pas na een spike te besluiten. De pilot kan mogelijk op
`RenderObservation.comparison`, `IssueOccurrence.evidence` en bestaande issues landen.

## 36. Open beslispunten

- Welke 8–12 regels vormen de eerste betrouwbare, actiegerichte set?
- Wordt de pilot alleen op staging/synthetische pagina's uitgevoerd of op één expliciet gekozen
  echte website met een harde limiet?
- Is componentgroepering op huidige DOM-signaturen stabiel genoeg zonder CMS-/templatekennis?
- Welke minimale volumes maken journey-frictie of een testkandidaat geloofwaardig per klanttype?
- Wanneer krijgt een incomplete axe-uitkomst een issue-status `review` en wanneer blijft zij alleen
  intern bewijs?
- Welke technische accessibility-uitkomst hoort later wel of niet in Effect?

## Besluit

Thactual kan geloofwaardig evolueren naar continuous website improvement zonder de huidige kern te
vervangen. Accessibility moet de eerste gecontroleerde testcase zijn voor meerdere signalen naar één
verbetering. De eerstvolgende implementatie hoort daarom een kleine accessibility-pilot te zijn,
niet een generiek platformproject.
