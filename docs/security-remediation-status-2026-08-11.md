# Security remediation status

**Peildatum:** 11 augustus 2026  
**Basis:** audit van 3 augustus 2026 en productie-evidence uit Release 7a  
**Doel:** actuele herstelstatus; dit document is geen onafhankelijke heraudit of penetratietest

## Samenvatting

Alle oorspronkelijke P0-bevindingen zijn technisch hersteld, met regressietests afgedekt en op
staging en productie gecontroleerd. Het oude `NO-GO` uit de audit blijft formeel van kracht totdat
ook de resterende P1-gates zijn afgerond en een onafhankelijke heraudit geen onbehandelde kritieke
of hoge bevindingen meer meldt.

## Herstelmatrix

| Bevinding | Status | Actueel bewijs |
|---|---|---|
| SEC-01 uitnodiging/accountovername | opgelost | bestaande accounts vereisen de bestaande sessie of het huidige wachtwoord; negatieve regressietest aanwezig |
| SEC-02 tenantrol omzeilt schrijfrechten | opgelost | schrijfrechten gebruiken de concrete tenantmembership; cross-tenant regressietests aanwezig |
| SEC-03 DNS-rebinding/SSRF | opgelost | gevalideerd IP wordt gepind met behoud van Host/SNI; redirects worden opnieuw gevalideerd; crawler-egress is netwerkmatig geïsoleerd |
| SEC-04 rechtstreekse API-publicatie | opgelost | productie en basis-Compose binden de API uitsluitend aan loopback |
| SEC-05 MFA en login-rate-limit | opgelost | MFA is verplicht voor beheerders; login en MFA hebben begrensde pogingen en security-auditregistratie |
| SEC-06 niet-intrekbare sessies | opgelost | server-side sessies, intrekking en kortere beheerderssessies zijn operationeel |
| SEC-07 globale API-key | operationeel opgelost | technische API-key wordt in productie geweigerd; workers gebruiken gescheiden database-identiteiten en queues |
| SEC-08 adminpromotie | opgelost | één tenantrolbeleid blokkeert onbevoegde admincreatie en beschermt de laatste beheerder |
| SEC-09 herbruikbare OAuth-state | opgelost | state is eenmalig en gebonden aan gebruiker, sessie, tenant en provider |
| SEC-10 CSRF | opgelost voor huidige cookieflows | centrale Origin-controle beschermt mutaties; productie weigert ontbrekende Origin bij cookiesessies |
| SEC-11 breed gedeelde secrets | grotendeels opgelost | secrets zijn per service begrensd, environmentbestanden vereisen veilige rechten en database-identiteiten zijn gescheiden |
| SEC-12 rootcontainers | opgelost binnen NAS-beperkingen | applicaties draaien niet-root, read-only, zonder capabilities en met `no-new-privileges`; alleen de niet-ondersteunde PID-limiet resteert als platformbeperking |
| SEC-13 back-upweerbaarheid | gedeeltelijk opgelost | versleutelde volledige herstelbundels, controles, privacy-ledger en periodieke taak werken; onafhankelijke immutable EU-kopie ontbreekt nog |
| SEC-14 auditlogging/detectie | gedeeltelijk opgelost | duurzaam security-auditregister bestaat; externe bescherming, detectieregels en incidentproef zijn nog niet volledig geaccepteerd |
| SEC-15 reproduceerbare supply chain | gedeeltelijk opgelost | gehashte locks, SHA-gepinde CI, SBOM en blokkerende scans draaien aantoonbaar op GitHub; drie cryptography-advisories en hoge/kritieke basisimagebevindingen houden de gate rood |
| SEC-16 betrouwbaar testbewijs | opgelost voor huidige suite | de volledige suite van 628 tests, Ruff, Bandit en secretscan is op GitHub/Python 3.12 geslaagd; de afzonderlijke securitybevindingen blijven onder SEC-15 open |

## Resterende securitygates

1. Configureer een onafhankelijke versleutelde EU-back-up met Object Lock of gelijkwaardige
   verwijderbescherming en bewijs een volledige restore vanuit uitsluitend die kopie.
2. Werk cryptography en beide basisimages bij zodra veilige uitgaven beschikbaar zijn en bewijs
   daarna een volledig groene dependency- en containeraudit; negeer of accepteer niets stilzwijgend.
3. Rond auditdetectie en incidentrespons af met beschermde opslag, concrete alerts en een
   operationele incidentproef.
4. Laat daarna een onafhankelijke heraudit en penetratietest uitvoeren en leg ASVS-L2-bewijs en
   eventuele expliciete risicoacceptaties vast.

De privacy-/contractgate, twee niet-technische onboardingproeven en homepagegoedkeuring blijven
afzonderlijke voorwaarden en worden niet door deze securitystatus vervangen.
