# Release 9 — Opportunity-engine en contextuele data-assistent

Status: op 7 augustus 2026 lokaal, op staging en op productie geaccepteerd vanaf releasecommit
`06f3863`.

## Doel en afbakening

Release 9 prioriteert aantoonbare kansen op basis van potentieel, beïnvloedbare frictie,
bewijskracht en uitvoerbaarheid/bereik. De score is geen algemene SEO-score en voorspelt geen
percentage extra verkeer. De eerste versie werkt zonder AI-provider en gebruikt uitsluitend
tenantgebonden gegevens die al in SEO Monitor aanwezig zijn.

## Fase 1 — Versieerbaar score- en bewijsfundament

- Migration `0055` voegt historische opportunity-evaluaties toe voor pagina's, URL-families en
  gedeelde oorzaken, zonder bestaande data te classificeren of te herschrijven.
- Iedere evaluatie bewaart analyseperiode, inputhash, formuleversie, vier afzonderlijke deelscores,
  totaalscore, prioriteitsklasse, brondekking, bijdragers en compact bewijs.
- De vaste formuleversie `opportunity-score-2026-08-07-v1` weegt potentieel 40%, beïnvloedbare
  frictie 25%, bewijskracht 20% en uitvoerbaarheid/bereik 15%.
- Ontbrekende dimensies blijven onbekend en leveren geen totaalscore. Bewijskracht onder 40 begrenst
  de uitkomst tot `insufficient_evidence`; middelmatige bewijskracht kan nooit een hoge kans maken.
- Dezelfde scope, inputhash en formuleversie maken geen dubbele historische evaluatie.
- De beveiligde lees-API retourneert uitsluitend evaluaties van een website binnen de
  geautoriseerde tenant. Automatische patroonberekening volgt in fase 2.

Acceptatie:

- alle deel- en totaalscores liggen tussen 0 en 100 en zijn herleidbaar tot centrale gewichten;
- ontbrekende data wordt niet als nul behandeld;
- lage bewijskracht kan geen hoge prioriteit opleveren;
- identieke input en formuleversie zijn idempotent;
- tenantoverschrijdend lezen wordt geweigerd;
- Alembic heeft één lineaire head op `0055`, Ruff en de gerichte tests slagen.

Lokale acceptatie:

- Alembic heeft één lineaire head op `0055`, direct vanaf `0054`.
- Ruff slaagt voor de volledige repository; alle nieuwe en gewijzigde Pythonbestanden voldoen aan
  de formattercontrole.
- De twee nieuwe score-, idempotentie-, historie-, API- en tenanttests en alle bestaande
  opportunity- en API-regressies slagen.
- De volledige testsuite slaagt met 468 tests en alleen de bestaande Starlette/httpx-waarschuwing.
- Migration `0055` is additief, voert geen backfill of dataherschrijving uit en vereist daarom geen
  extra releaseback-up.

## Fase 2 — Eerste deterministische opportunitypatronen

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Een expliciete evaluatieactie combineert bestaande GSC-paginametrics met actieve, passende
  crawlerissues en schrijft uitsluitend nieuwe historische evaluaties weg.
- Een CTR-kans vereist minimaal 250 vertoningen, gemiddelde positie 4–15, CTR onder 2,5% en een
  actieve title- of meta-descriptionfrictie.
- Een pagina-twee-kans vereist minimaal 150 vertoningen, positie 11–20, een actuele zekere
  niet-gemengde intentieclassificatie en actieve thin- of near-duplicate-contentfrictie.
- Een interne-linkkans vereist minimaal 150 vertoningen, crawldiepte vier of hoger en een actief
  diepte- of interne-ondersteuningsissue.
- Iedere evaluatie bewaart positieve, negatieve en contextuele bijdragers plus GSC- en issuebewijs.
  De patroonversie is expliciet en dezelfde periode/input blijft idempotent.
- Alleen actieve, indexeerbare URL's met status 200 komen in aanmerking. Functionele zoekpagina's,
  discovery-only varianten en issues met opgelost, geverifieerd, genegeerd of geaccepteerd risico
  leveren geen kans op.
- De meetperiode omvat minimaal 28 dagen. Ontbrekende analyticsdekking blijft zichtbaar en wordt
  niet als nul geïnterpreteerd.

Acceptatie:

- ieder patroon vereist zowel meetbaar potentieel als een aannemelijk beïnvloedbare frictie;
- drempels, formule- en patroonversie en alle bijdragers zijn uitlegbaar;
- dezelfde input maakt geen dubbele evaluatie;
- functionele pagina's en geaccepteerde risico's leveren geen schijnkans;
- gerichte patroon- en regressietests, Ruff en de volledige testsuite slagen.

Lokale acceptatie:

- Twee gerichte tests bevestigen alle drie patronen, bewijsopbouw, idempotentie, functionele-
  paginafilters, geaccepteerd risico en de minimale periode.
- De API-regressie bevestigt dat evaluaties niet buiten de geautoriseerde tenant kunnen worden
  gestart.
- Ruff en de formattercontrole voor de fasebestanden slagen; Alembic blijft op de lineaire head
  `0055` en deze fase vereist geen nieuwe migration.
- De volledige testsuite slaagt met 470 tests en alleen de bestaande Starlette/httpx-waarschuwing.

## Fase 3 — Transparante API en interface

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Het bestaande Contentscherm toont historische kansbeoordelingen zonder nieuwe hoofdnavigatie.
- Iedere beoordeling toont de vier deelscores, totaalscore, prioriteitsklasse, bijdragers,
  brondekking, formuleversie en het verschil met de vorige meting van dezelfde scope.
- Ontbrekende bronnen blijven expliciet `onbekend`; een ontbrekende score wordt niet als nul
  gepresenteerd. De onderliggende bijdragers zijn op aanvraag zichtbaar.
- Berekenen gebeurt uitsluitend via de expliciete knop `Bereken kansen`; laden van het scherm
  wijzigt geen data en activeert geen contentwijziging.
- Een bruikbare kans kan handmatig naar de bestaande taakworkflow worden gepromoveerd. Een actieve
  taak voor hetzelfde patroon en dezelfde scope wordt hergebruikt, zodat herhaald klikken geen
  duplicaat maakt. Beoordelingen met onvoldoende bewijs kunnen geen taak worden.
- De taak bewaart de evaluatie-, scope-, patroon- en formuleversie als verificatiecontext en koppelt
  de primaire URL en geldige onderliggende issues.

Acceptatie:

- alle scores en ontbrekende dekking zijn zichtbaar en herleidbaar;
- een vorige meting wordt alleen binnen dezelfde scope en formuleversie vergeleken;
- berekenen en taakpromotie zijn expliciete gebruikersacties;
- taakpromotie is tenantgebonden en dedupliceert actieve taken;
- de bestaande contentcontrolepunten blijven beschikbaar naast de gescoorde kansen;
- API-, UI-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De API- en UI-regressies bevestigen URL-weergave, historische vergelijking, expliciete acties,
  tenantisolatie en hergebruik van een bestaande actieve taak.
- De fasebestanden voldoen aan Ruff en de JavaScript-syntaxcontrole; Alembic blijft op de lineaire
  head `0055` en deze fase vereist geen migration.
- De volledige testsuite slaagt met 472 tests en alleen de bestaande Starlette/httpx-waarschuwing.

## Fase 4 — Leesbaar en tenantgebonden assistentfundament

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Een nieuw read-only antwoordendpoint behandelt vragen binnen één expliciet zichtbaar issue of
  één opportunity-evaluatie. Website, contexttype en record-ID vormen samen de verplichte scope.
- Antwoorden scheiden gemeten feiten, productinterpretaties, ontbrekend bewijs, confidence en
  verwijzingen naar de gebruikte interne bronrecords.
- Issue-antwoorden gebruiken uitsluitend de actuele issue-lifecycle, nieuwste opgeslagen
  waarneming, betrokken URL en bestaande versieerbare issue-uitleg.
- Opportunity-antwoorden gebruiken uitsluitend de historische deelscores, formuleversie,
  meetperiode en brondekking. Ontbrekende bronnen blijven onbekend en worden niet als nul behandeld.
- De eerste versie is deterministisch en gebruikt geen AI-provider. Dezelfde vraag en context
  leveren dezelfde feitelijke kern op.
- Algemene marktvergelijkingen, concurrentvragen en externe tooladviezen krijgen een korte
  scopebegrenzing en worden niet via een publieke antwoordroute afgehandeld.
- Het endpoint kan geen crawl, taak, export, statuswijziging of andere mutatie starten.

Acceptatie:

- een contextrecord buiten de gekozen website of tenant wordt niet zichtbaar;
- ieder inhoudelijk antwoord noemt bronrecords en meetmomenten waar die beschikbaar zijn;
- ontbrekend technisch bewijs verlaagt de confidence en blijft expliciet zichtbaar;
- herhaalde identieke vragen schrijven niets en geven dezelfde feitelijke uitkomst;
- scopevreemde vragen leveren geen externe aanbeveling of verzonnen klantdata;
- API-, tenantisolatie-, read-only-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De gerichte regressie bevestigt deterministische issue- en opportunity-antwoorden, expliciet
  ontbrekend bewijs, interne bronverwijzingen, scopebegrenzing en tenantisolatie.
- Voor en na de antwoordaanvragen blijven aantallen taken, activiteiten en crawljobs ongewijzigd.
- Ruff slaagt voor de volledige repository; Alembic blijft op de lineaire head `0055` en deze fase
  vereist geen migration.
- De volledige testsuite slaagt met 473 tests en alleen de bestaande Starlette/httpx-waarschuwing.

## Fase 5 — Contextassistent in de bestaande interface

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Het bestaande issuedetail bevat een compacte vraagsectie die automatisch aan het zichtbare issue
  en de geselecteerde website is gebonden.
- Iedere gescoorde kans bevat een afzonderlijk inklapbaar vraagformulier dat uitsluitend de
  betreffende opportunity-evaluatie als context meestuurt.
- Vragen worden alleen na expliciet verzenden beantwoord. Openen of laden van een scherm start geen
  aanvraag en veroorzaakt geen taak, crawl, export of statuswijziging.
- Antwoorden tonen gemeten feiten, productinterpretaties, ontbrekend bewijs en gebruikte interne
  bronnen in afzonderlijke kaarten, inclusief confidence en beschikbare meetmomenten.
- Scopebegrenzingen en fouten verschijnen lokaal bij de vraag. Er is geen nieuwe hoofdnavigatie,
  chatgeschiedenis of koppeling met de publieke homepageassistent.
- De vormgeving blijft bruikbaar op 390 px: antwoordkaarten gaan terug naar één kolom en
  tekstvelden blijven binnen de beschikbare breedte.

Acceptatie:

- het issuedetail verstuurt altijd het geselecteerde issue-ID en de geselecteerde website;
- een kansvraag verstuurt altijd het bijbehorende historische evaluation-ID;
- antwoordonderdelen worden gescheiden en alle servertekst wordt veilig als tekst gerenderd;
- laden, sluiten en opnieuw openen van context wist een eerder lokaal antwoord;
- de interface bevat geen impliciete mutatie of externe toolroute;
- UI-, JavaScript-, API-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De UI-regressie bevestigt beide contextformulieren, de afzonderlijke stylesheet en de expliciete
  submitroute; de bestaande contextassistent-API- en tenanttests blijven groen.
- Een visuele controle op 390 px bevestigt een viewportbrede pagina zonder horizontale overflow,
  éénkoloms antwoordkaarten en een tekstveld binnen de beschikbare kaartbreedte.
- Dynamische vraagvelden hebben een uniek label, servertekst wordt ge-escaped en ieder antwoord
  vermeldt dat de route alleen-lezen is.
- Ruff, JavaScript-syntaxcontrole en de volledige testsuite met 473 tests slagen; Alembic blijft op
  head `0055` en deze fase vereist geen migration of extra releaseback-up.

## Fase 6 — Gelijkwaardige leadperioden en pagina-aandrijvers

Status: lokaal geïmplementeerd en nog niet gedeployed.

- De contextassistent ondersteunt een expliciete websiteperformancecontext met een einddatum en
  een periode van 28 tot en met 90 kalenderdagen.
- De gekozen periode wordt vergeleken met de direct voorafgaande periode met hetzelfde aantal
  dagen, dezelfde kalenderperiode één jaar eerder en dezelfde periode twee jaar eerder.
- Alleen de ingestelde primaire analyticsbron wordt gebruikt. GA4 en Matomo worden niet
  gecombineerd en analyticsbezoeken worden niet bij GSC-klikken opgeteld.
- Iedere bekende periode toont organische sessies/bezoeken, gekwalificeerde leads en de afgeleide
  conversieratio. Een periode zonder aantoonbare bronregels of volledige grensdekking blijft
  `onbekend` en wordt niet als nul gepresenteerd.
- De vijf pagina's met de grootste absolute leadverandering worden gerangschikt. Per pagina splitst
  een rekenkundige decompositie de bijdrage van veranderd verkeer en veranderde conversieratio.
- De uitkomst benoemt expliciet dat dit geobserveerde samenhang is. Zonder aanvullend bewijs wordt
  geen crawlwijziging, taak of andere gebeurtenis als oorzaak aangewezen.
- De berekening is read-only, deterministisch, tenantgebonden en vereist geen AI-provider.

Acceptatie:

- iedere vergelijking gebruikt exact evenveel kalenderdagen;
- één- en tweejaarshistorie wordt alleen getoond wanneer de bron het bereik aantoonbaar dekt;
- pagina-aandrijvers tonen verkeer en conversieratio afzonderlijk;
- ontbrekende historie verlaagt confidence en blijft onbekend;
- een andere website-ID kan niet als performancecontext worden gebruikt;
- de endpointvalidatie vereist een einddatum en accepteert uitsluitend perioden van 28–90 dagen;
- GA4-, Matomo-, contextassistent-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De nieuwe regressie bevestigt de huidige en direct voorgaande 28-daagse periode, beschikbare
  jaarhistorie, onbekende tweejaarshistorie en twee tegengestelde pagina-aandrijvers.
- De test maakt zichtbaar dat een stijgende pagina vooral door conversieratio verandert en een
  dalende pagina vooral door verkeer, zonder daar een causale verklaring aan te koppelen.
- Ontbrekende einddatum levert validatiefout `422`; een afwijkend websitecontext-ID wordt geweigerd.
- De bestaande Matomo-providerregressies, Ruff en de volledige testsuite met 474 tests slagen;
  Alembic blijft op head `0055` en deze fase vereist geen migration of extra releaseback-up.

## Fase 7 — Leadvergelijking in het Inzichtenscherm

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Het bestaande Inzichtenscherm bevat een contextgebonden vraagformulier voor organische
  leadontwikkeling, zonder nieuwe navigatie of los chatvenster.
- De geselecteerde website, gekozen periode van 28 of 90 dagen en gisteren als volledig afgesloten
  einddatum vormen expliciet de aanvraagcontext.
- Alleen een expliciete submit verstuurt de vraag. Het laden of verversen van Inzichten start geen
  assistentaanvraag en veroorzaakt geen mutatie.
- Het antwoord hergebruikt de bestaande gescheiden presentatie voor feiten, interpretatie,
  ontbrekend bewijs en interne bronnen. Pagina-aandrijvers blijven tekstueel herleidbaar tot
  verkeer en conversieratio.
- Een website- of periodewissel wist het lokale antwoord, zodat een resultaat nooit zichtbaar
  blijft onder een andere context.
- De primaire analyticsbron blijft leidend; de interface suggereert niet dat GA4 en Matomo worden
  gecombineerd of dat samenhang causaliteit bewijst.

Acceptatie:

- iedere aanvraag bevat website-ID, websiteperformancecontext, einddatum en gekozen dagenaantal;
- alleen 28 of 90 dagen kunnen vanuit deze interface worden verstuurd;
- servertekst wordt ge-escaped en fouten blijven lokaal bij het formulier;
- website- en periodewissels verwijderen het vorige antwoord;
- UI-, JavaScript-, API-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De UI-regressie bevestigt formulier, antwoordgebied, websiteperformancecontext en doorgegeven
  dagenaantal; de bestaande API- en tenanttests blijven groen.
- De einddatum gebruikt de lokale kalenderdag en voorkomt daardoor een UTC-dagverschuiving rond
  middernacht in de ingestelde tijdzone.
- Ruff, JavaScript-syntaxcontrole en de volledige testsuite met 475 tests slagen; Alembic blijft op
  head `0055` en deze fase vereist geen migration of extra releaseback-up.

## Fase 8 — Analytics-meetkwaliteit vóór leadconclusies

Status: lokaal geïmplementeerd en nog niet gedeployed.

- GA4-leadvergelijkingen gebruiken voortaan uitsluitend de events die bij de actieve GA4-koppeling
  expliciet als gekwalificeerde lead zijn geselecteerd. De generieke `key_events`-teller wordt niet
  meer stilzwijgend als gekwalificeerde lead geïnterpreteerd.
- Een read-only kwaliteitslaag vergelijkt geselecteerde events per dag en gekoppelde landingspagina
  met de organische sessies van diezelfde dag en URL.
- Minimaal tien events met nul sessies of ten minste drie events per sessie vormen een sterke
  meetafwijking. Dit is een conservatieve eerste regel en geen universele conversiegrens.
- Verdachte events worden nooit verwijderd of in de database gecorrigeerd. Het antwoord toont het
  ruwe totaal én een gevoeligheidsberekening zonder de verdachte bijdrage.
- Zodra de huidige of vorige periode een sterke afwijking bevat, daalt confidence naar `low`,
  vervallen pagina-aandrijvers en volgt geen conclusie over groei of daling. De gebruiker krijgt
  eerst een concrete trackingcontrole met datum, genormaliseerde URL, eventvolume en sessievolume.
- Matomo blijft via de eigen geaggregeerde conversiedata lopen en wordt niet met GA4-events
  gecombineerd. De bestaande expliciete primaire-bronkeuze blijft leidend.
- De kwaliteitscontrole is tenantgebonden, deterministisch en read-only; issue-lifecycle en
  verificatiehistorie volgen pas in een afzonderlijke fase.

Acceptatie:

- niet-geselecteerde GA4-events tellen niet als leads;
- een sterke event-/sessieafwijking is zichtbaar vóór iedere conversieconclusie;
- ruwe en gevoeligheidsberekende totalen blijven naast elkaar beschikbaar;
- verdachte bronregels blijven ongewijzigd opgeslagen;
- bij een meetafwijking worden geen pagina- of oorzakelijke aanbevelingen gegeven;
- GA4-, Matomo-, contextassistent-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De regressie gebruikt bewust afwijkende generieke GA4-`key_events` en bevestigt dat alleen de
  expliciet geselecteerde events meetellen als gekwalificeerde leads.
- Een meetafwijking van 20 events bij 2 sessies toont 31 ruwe tegenover 11
  gevoeligheidsberekende leads, verlaagt confidence en onderdrukt lead- en pagina-conclusies.
- Na de kwaliteitswaarschuwing bevat het oorspronkelijke bronrecord nog steeds exact 20 events;
  de controle is daarmee aantoonbaar read-only.
- De bestaande Matomo-regressies, Ruff en de volledige testsuite met 475 tests slagen; Alembic
  blijft op head `0055` en deze fase vereist geen migration of extra releaseback-up.

## Fase 9 — Persistente GA4-meetkwaliteitsissues

Status: lokaal geïmplementeerd en nog niet gedeployed.

- Iedere geslaagde GA4-synchronisatie voert na opslag van de ruwe bronregels dezelfde
  event-/sessiekwaliteitscontrole uit als de contextassistent.
- Een sterke afwijking wordt per website en URL als `ga4_event_session_anomaly` opgeslagen. De
  bestaande unieke issue-identiteit voorkomt duplicaten bij herhaalde synchronisaties.
- Iedere controle bewaart periode, uitkomst en concrete event-, sessie-, datum- en URL-bewijzen in
  de bestaande activiteitenhistorie; de ruwe GA4-regels blijven ongewijzigd.
- De eerste schone controle zet een actief meetkwaliteitsissue op `resolved`; een tweede schone
  controle zet het op `verified`. Een nieuwe afwijking opent een opgelost of geverifieerd issue
  opnieuw.
- Genegeerde en geaccepteerde-risico-uitkomsten worden bij een schone controle niet automatisch
  overschreven. De kwaliteitscontrole blokkeert geen crawl of technische onboarding.
- De synchronisatierespons rapporteert aantallen afwijkingen, nieuwe, opgeloste en geverifieerde
  issues voor operationele controle.

Acceptatie:

- herhaalde afwijkingen maken geen dubbel issue;
- bewijs en controle-uitkomst blijven per synchronisatie herleidbaar;
- twee opeenvolgende schone controles doorlopen `resolved` en `verified`;
- een terugkerende afwijking heropent hetzelfde issue;
- generieke GA4-`key_events` blijven buiten de gekwalificeerde leadcontrole;
- issue-, GA4-, contextassistent-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- Eén regressieketen bevestigt achtereenvolgens aanmaken, dedupliceren, oplossen, verifiëren en
  heropenen van exact hetzelfde meetkwaliteitsissue.
- De vijf controles bewaren ieder hun eigen uitkomst; het eerste bewijs bevat aantoonbaar 20
  geselecteerde events bij 2 sessies terwijl de generieke teller van 999 wordt genegeerd.
- De bestaande GA4-synchronisatie-, contextassistent- en issue-lifecycleregressies blijven groen.
- Ruff en de volledige testsuite met 476 tests slagen; Alembic blijft op head `0055` en deze fase
  vereist geen migration of extra releaseback-up.

## Fase 10 — Meetkwaliteitsstatus voor GA4 én Matomo

Status: lokaal geïmplementeerd en nog niet gedeployed.

- De Integratiespagina toont bij de gekozen primaire analyticsbron één duidelijke status:
  `Nog niet ingesteld`, `Nog niet gevalideerd`, `Aandacht nodig`, `Voorlopig hersteld` of
  `Metingen betrouwbaar`.
- De kaart benoemt expliciet GA4 of Matomo. Een bronwissel laadt alleen de status van de nieuwe
  primaire bron; meetwaarden en issues van beide providers worden nooit gecombineerd.
- GA4 blijft uitsluitend geselecteerde gekwalificeerde events tegenover organische sessies
  controleren. Matomo controleert afzonderlijk de eigen pagina-conversies tegenover bezoeken.
- Dezelfde conservatieve eerste afwijkingsregel geldt voor beide bronnen: minimaal tien
  conversies met nul bezoeken of minimaal drie conversies per bezoek.
- Matomo-afwijkingen krijgen een eigen gededupliceerd `matomo_conversion_visit_anomaly`-issue met
  dezelfde bewijs-, herstel-, verificatie- en heropeningshistorie als GA4.
- Na een handmatige synchronisatie of wijziging van bron of GA4-eventselectie wordt de zichtbare
  status direct opnieuw geladen. Servertekst wordt veilig als tekst gerenderd.

Acceptatie:

- GA4 en Matomo tonen ieder hun eigen bronnaam, bewijs en status;
- een Matomo-afwijking maakt geen GA4-issue en omgekeerd;
- twee schone Matomo-controles doorlopen `resolved` en `verified`;
- de interface toont bewijsvolume, bezoekvolume en controledatum zonder ruwe data te wijzigen;
- bronwissel en synchronisatie verversen de status zonder nieuwe navigatie;
- GA4-, Matomo-, API-, UI-, JavaScript-, lint- en regressietests slagen zonder nieuwe migration.

Lokale acceptatie:

- De GA4-regressie toont `Aandacht nodig` voor 20 geselecteerde events bij 2 sessies en negeert de
  afwijkende generieke teller; bronlabel en laatste bewijs blijven zichtbaar.
- De Matomo-regressie toont ook zonder voorafgaand issue na één schone controle `Voorlopig
  hersteld` en na twee controles `Metingen betrouwbaar`; 20 conversies bij 2 bezoeken maken daarna
  één eigen issue dat opnieuw via `resolved` en `verified` wordt gecontroleerd.
- De UI-regressie bevestigt de providerneutrale statuskaart en beveiligde kwaliteitsroute; de
  JavaScript-syntaxcontrole slaagt.
- Ruff en de volledige testsuite met 478 tests slagen; Alembic blijft op head `0055` en deze fase
  vereist geen migration of extra releaseback-up.

## Fase 11 — Integrale lokale acceptatie

Status: lokaal, op staging en op productie afgerond.

- Release 9 omvat het versieerbare opportunityfundament, drie eerste deterministische patronen,
  transparante taakpromotie, de tenantgebonden contextassistent, periodevergelijkingen voor
  organische leads en providergebonden meetkwaliteitsbewaking.
- Opportunityscores blijven uitleggen welke dimensies en bronnen bijdragen; ontbrekende data wordt
  niet als nul behandeld en lage bewijskracht kan geen hoge prioriteit opleveren.
- Assistentantwoorden blijven read-only en scheiden feiten, interpretatie en ontbrekend bewijs.
  Samenhang wordt niet als oorzaak gepresenteerd.
- GA4 en Matomo blijven afzonderlijke primaire bronnen. Een sterke meetafwijking begrenst
  leadconclusies en volgt als gededupliceerd issue de bestaande lifecycle.
- Er is geen externe AI-provider, SERP-bron of nieuwe algemene SEO-score toegevoegd.

Lokale acceptatie:

- Ruff slaagt voor de volledige repository en de JavaScript-syntaxcontrole van de interface is
  groen.
- De volledige testsuite slaagt met 478 tests en alleen de bestaande Starlette/httpx-waarschuwing.
- Alembic heeft één lineaire head op `0055`; alleen de additieve opportunitymigration uit fase 1
  is toegevoegd en bestaande data wordt niet herschreven.
- De basisconfiguratie en productie-override zijn samen geldig; de zelfstandige stagingconfiguratie
  is eveneens geldig met `.env.example`.
- De release start bij laden geen crawl, import, taak of andere mutatie. Berekenen, synchroniseren,
  vragen en taakpromotie blijven expliciete gebruikersacties.
- De migration is additief en de overige fasen wijzigen geen schema. Een extra releaseback-up is
  daarom niet nodig; de bestaande geverifieerde herstelroute blijft een deploymentvoorwaarde.

Stagingacceptatie:

- Releasecommit `06f3863` is via het vaste Git-archive en de interactieve NAS-route gedeployed.
- API, PostgreSQL en Redis zijn gezond op migration-head `0055`; PageSpeed en
  JavaScript-rendering blijven uitgeschakeld en alle Release-9-routes zijn aanwezig.
- De synthetische stagingwebsite bevat bewust geen gekoppelde analytics of classificeerbare
  crawldata. Content, kansen en Inzichten tonen daardoor correcte lege toestanden zonder een
  berekening, import, crawl of assistentaanvraag te starten.
- De contextassistent, expliciete knop `Bereken kansen` en providerneutrale analyticskwaliteitskaart
  zijn aanwezig. Providerlogica en tenantisolatie blijven door de volledige regressieset gedekt.
- De gemeten content-, doorstroom- en score-endpoints reageerden in 89–100 ms.
- Op desktop en 390 px waren document- en viewportbreedte exact gelijk. Er was geen interne
  overflow en de browser rapporteerde geen fouten of waarschuwingen.

Productieacceptatie:

- Releasecommit `06f3863` is via het vaste Git-archive en de interactieve NAS-route gedeployed.
- API, integration-worker, PostgreSQL en Redis zijn gezond op migration-head `0055`; PageSpeed en
  JavaScript-rendering blijven voor API en integration-worker uitgeschakeld en alle
  Release-9-routes zijn aanwezig.
- De veilige hervattingscontrole rapporteert geen actieve of wachtende deploymenttaken en heeft
  geen impliciete actie uitgevoerd.
- Content, Kansen, Inzichten en Integraties laden met productiedata zonder bij navigatie een crawl,
  import, berekening of assistentaanvraag te starten.
- GA4 is expliciet opgeslagen als primaire analyticsbron voor de gecontroleerde website; de
  gekoppelde GA4-property, historische import en het gekwalificeerde event `form_submit` blijven
  behouden. De kwaliteitskaart toont terecht `GA4: Nog niet gevalideerd` totdat een volgende
  GA4-synchronisatie de meetkwaliteit controleert.
- Op 390 px waren viewport-, document- en bodybreedte exact 390 px. Er was geen documentoverflow
  en de browser rapporteerde geen fouten of waarschuwingen.
