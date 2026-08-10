# Release 14 — Invitation-only onboarding

Status: fase A tot en met D lokaal en op staging geaccepteerd; nog niet op productie gedeployed.

## Doel

Een uitgenodigde gebruiker kan zonder terminal- of databasehandeling een website toevoegen,
eigendom bewijzen, veilige crawlvoorkeuren bevestigen en daarna exact één eerste crawl starten. De
flow is hervatbaar en tenantgebonden. Sensor blijft uit totdat websiteverificatie, privacyprofiel en
een afzonderlijk live-activeringsbesluit zijn afgerond.

## Fase A — persistente onboarding en eigendomsverificatie

- aparte friends-and-family-route naast de bestaande beheerdersaanmaak;
- idempotente start via een clientrequest-ID;
- website en instellingen worden atomair met een persistente onboardingstatus aangemaakt;
- de website blijft `verification_pending` en er wordt nog geen crawljob gemaakt;
- één HTTPS-bestand onder `/.well-known/thactual-verification.txt` is de eerste verificatiemethode;
- alleen SHA-256 van het willekeurige token wordt opgeslagen; de inhoud wordt alleen bij eerste
  aanmaak teruggegeven;
- controle hergebruikt timeout-, responsegrootte-, redirect- en SSRF-beveiliging;
- redirects buiten de exacte website-origin, verkeerde inhoud en verlopen tokens zijn
  herstelbare statussen;
- succes activeert de website en brengt de flow naar crawlvoorkeuren, maar start nog geen crawl;
- start en verificatiecontrole krijgen security-auditbewijs zonder token of responsecontent.

Lokale acceptatie:

- 17 gerichte onboarding-, security- en migratietests geslaagd;
- volledige regressiesuite: 597 geslaagd met alleen de bestaande dependencywaarschuwing;
- Alembic heeft één lineaire head `0062`;
- gewijzigde Pythonbestanden zijn lintvrij en correct geformatteerd;
- privacyverwijdering wist onboarding- en verificatierecords expliciet vóór websiteverwijdering.

Stagingacceptatie:

- Alembic staat op één head `0062`;
- herhaald starten is idempotent en maakt geen dubbele website aan;
- alleen de SHA-256-hash van het verificatietoken wordt opgeslagen;
- vóór succesvolle verificatie worden nul crawljobs aangemaakt;
- de drie beveiligde onboardingroutes zijn beschikbaar;
- de acceptatiefixture is volledig opgeruimd;
- API en database zijn gezond;
- definitief gereedsignaal: `release-14-phase-a-staging-ok`.

Fase B voegt tokenvernieuwing/download en de begeleide verificatie-interface toe. Latere fasen
voegen idempotent starten van de eerste crawl, begrijpelijke voortgang,
analytics/Sensor-meetvalidatie en end-to-end gebruikersproeven toe.

## Fase B — begeleide verificatie

- een hervatbare tweestapsinterface maakt de website aan en begeleidt de bestandsplaatsing;
- het verificatiebestand wordt rechtstreeks gedownload zonder tokenweergave in de interface;
- opnieuw downloaden vernieuwt het token, de vervaldatum en de opgeslagen hash atomair;
- oude bestanden worden daarmee direct ongeldig en tokens komen niet in logs of blijvende
  browseropslag;
- begrijpelijke meldingen vervangen technische foutcodes;
- succesvolle controle brengt de gebruiker naar de crawlvoorkeuren zonder al een crawl te starten.

Lokale acceptatie:

- 66 gerichte API-, onboarding- en interfacetests geslaagd;
- volledige regressiesuite geslaagd met alleen de bestaande dependencywaarschuwing;
- Python-linting, formattingcontrole en JavaScript-syntaxcontrole geslaagd;
- geen migration nodig: fase B gebruikt de persistente modellen uit `0062`.

Stagingacceptatie:

- tokenvernieuwing vervangt aantoonbaar de oude hash en reset de pogingsteller;
- uitsluitend de hash blijft opgeslagen en het token komt niet in blijvende browseropslag;
- vóór verificatie worden nul crawljobs aangemaakt;
- de begeleide interface en hervatten na refresh zijn aanwezig;
- desktop- en mobiele browserweergave zijn helder, toegankelijk en vrij van consolefouten;
- de synthetische fixture is volledig opgeruimd;
- API en database zijn gezond en Alembic staat op `0062`;
- definitief gereedsignaal: `release-14-phase-b-staging-ok`.

## Fase C — veilige eerste crawl

- na eigendomsverificatie bevestigt de gebruiker voorzichtige crawlvoorkeuren;
- robots.txt respecteren is tijdens onboarding verplicht;
- standaard wordt maximaal 1.000 pagina's gecontroleerd met 300 ms vertraging en drie
  gelijktijdige verzoeken;
- één persistente `first_crawl_job_id` maakt dubbel klikken, refresh en herhaalde API-verzoeken
  idempotent;
- de eerste crawl wordt pas na verificatie en buiten een deployment-drain aangemaakt;
- de interface hervat na refresh met dezelfde crawljob en toont de actuele wachtrijstatus;
- Alembic heeft één lineaire head `0063`.

Lokale acceptatie:

- 71 gerichte onboarding-, migratie-, API- en interfacetests geslaagd;
- volledige regressiesuite geslaagd met alleen de bestaande dependencywaarschuwing;
- Python-linting, formattingcontrole en JavaScript-syntaxcontrole geslaagd;
- dubbel starten levert dezelfde crawljob op en bewaart de oorspronkelijk bevestigde instellingen.

Stagingacceptatie:

- Alembic staat op één head `0063`;
- herhaald starten levert exact dezelfde eerste crawljob op;
- de veilige instellingen en verplichte robots.txt-keuze zijn opgeslagen;
- de fixture maakte één databasejob en stuurde nul jobs naar Redis of een echte website;
- hervatten na refresh is aanwezig;
- de driestapsflow en veilige standaardwaarden zijn op desktop en mobiel helder weergegeven;
- robots.txt is in de interface zichtbaar verplicht en niet uitschakelbaar;
- de browserconsole bevat geen fouten of waarschuwingen;
- de synthetische fixture is volledig opgeruimd en API en database zijn gezond;
- definitief gereedsignaal: `release-14-phase-c-staging-ok`.

## Fase D — begrijpelijke voortgang en herstel

- onboarding volgt de bestaande eerste crawljob en maakt geen tweede voortgangsmodel;
- wachtrij, uitvoering, crawlstadium en aantallen worden automatisch iedere vier seconden ververst;
- technische crawlstadia worden vertaald naar begrijpelijke gebruikersmeldingen;
- de flow blijft na refresh hervatbaar met hetzelfde onboarding- en crawljob-ID;
- succes en gedeeltelijk succes openen rechtstreeks de eerste inzichten;
- een mislukte of geannuleerde crawl geeft een herstelactie zonder instellingen te verliezen;
- opnieuw proberen zet dezelfde crawljob terug in de wachtrij en maakt geen duplicaat.

Lokale acceptatie:

- 71 gerichte onboarding-, API- en interfacetests geslaagd;
- volledige regressiesuite geslaagd met alleen de bestaande dependencywaarschuwing;
- Python-linting en JavaScript-syntaxcontrole geslaagd;
- voortgang, eindstatus, foutstatus en hergebruik van hetzelfde job-ID zijn afgedekt;
- geen migration nodig: fase D gebruikt de bestaande modellen en Alembic-head `0063`.

Stagingacceptatie:

- dezelfde synthetische crawljob werd zichtbaar hervat na een volledige paginaverversing;
- de fase `sitemap_import` verscheen begrijpelijk als `Sitemap wordt gelezen`;
- gevonden, gecontroleerde en mislukte aantallen werden correct bijgewerkt;
- gedeeltelijk succes opende `Bekijk eerste inzichten` en selecteerde de juiste website;
- een gecontroleerde fout gaf een begrijpelijke herstelmelding en alleen `Opnieuw proberen`;
- veilig opnieuw proberen hergebruikte aantoonbaar hetzelfde job-ID en maakte nul duplicaten;
- er werd geen echte website gecrawld en niets naar Redis gestuurd tijdens de fixtureproef;
- de synthetische website, onboarding, verificatie, job en crawlrun zijn volledig opgeruimd;
- API en database bleven gezond op Alembic-head `0063`;
- definitief gereedsignaal: `release-14-phase-d-staging-ok`.

## Fase E — optionele meetkwaliteit

- technische onboarding en crawling blijven volledig bruikbaar zonder analyticskoppeling;
- het onboardingresultaat hergebruikt de bestaande GA4/Matomo-meetkwaliteitsstatus;
- conversie-inzichten krijgen alleen bij status `reliable` het label betrouwbaar;
- `not_configured`, `insufficient_data`, `attention_needed` en `provisional` krijgen een eerlijke,
  begrijpelijke toelichting zonder technische details;
- de gebruiker kan vanuit het resultaat rechtstreeks naar Integraties om bron en leadevents in te
  stellen;
- er ontstaat geen tweede kwaliteitsengine of afwijkende bronlogica.

Lokale acceptatie:

- onboarding zonder analytics blijft voltooid en zet `conversion_insights_reliable` op `false`;
- een bestaande betrouwbare Matomo-controle wordt correct als `reliable` doorgegeven;
- alle vijf kwaliteitsstatussen hebben een afzonderlijke, begrijpelijke gebruikersmelding;
- de configuratieactie opent Integraties met dezelfde klant en website geselecteerd;
- gerichte onboarding-, analytics-, API- en interfacetests zijn geslaagd;
- de volledige regressiesuite is geslaagd met alleen de bestaande dependencywaarschuwing;
- Python-linting en JavaScript-syntaxcontrole zijn geslaagd;
- geen migration nodig: fase E gebruikt de bestaande analyticsrecords en Alembic-head `0063`.
