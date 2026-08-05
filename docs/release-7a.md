# Release 7a — Privacy- en beveiligingsgate

## Release 7a-A — Identiteit en toegang

Status: lokaal afgerond en integraal getest; nog niet op staging of productie gedeployed.

Deze eerste deelrelease sluit de kritieke account- en tenanttoegangsrisico's uit de audit van
3 augustus 2026:

- uitnodigingen kunnen het wachtwoord van een bestaand account niet vervangen;
- schrijfrechten worden afgedwongen op de rol binnen de betreffende tenant;
- sessies zijn server-side, intrekbaar en worden ingetrokken bij uitloggen, rolwijziging en
  toegangsverwijdering;
- OAuth-state is eenmalig en gebonden aan gebruiker, sessie, tenant en provider;
- login-rate-limiting, request-origincontrole en MFA voor beheerders zijn aanwezig;
- MFA ondersteunt TOTP en eenmalige herstelcodes; mislukte MFA-pogingen vallen onder de rate-limit;
- tenantbeheerders kunnen geen andere beheerder creëren en de laatste tenantbeheerder blijft
  beschermd;
- login, MFA, uitnodigingen en toegangswijzigingen komen zonder secrets of bronadres in een
  afzonderlijk beveiligingsauditregister;
- de algemene technische API-key wordt in productie altijd geweigerd. De huidige workers gebruiken
  geen HTTP-API-key en werken rechtstreeks via hun database- en queueverbinding.

De release bevat migraties `0046` tot en met `0051`. Migratie `0046` trekt bestaande openstaande
uitnodigingen preventief in; de overige migraties zijn additief. Maak daarom vóór deployment een
geverifieerde databaseback-up en controleer na migratie expliciet dat Alembic `0051` meldt.

Voor productie moet `MFA_ENFORCEMENT_ENABLED=true` actief zijn. `API_KEY` blijft leeg en kan geen
productietoegang geven. De API blijft uitsluitend via de bestaande loopbackbinding en HTTPS-reverse
proxy bereikbaar.

Lokale acceptatie:

- Ruff: geslaagd;
- volledige testsuite: 428 tests geslaagd;
- Alembic: één head, `0051`;
- JavaScript-rendering en PageSpeed blijven uitgeschakeld;
- de Linux-worker blijft buiten deze release.

Productieacceptatie volgt pas na staging, gecontroleerde deployment en functionele verificatie van
persoonlijk inloggen, verplichte MFA, sessie-intrekking, tenantrollen, OAuth-state en auditregistratie.

## Release 7a-B — Platform en privacy

Status: gepland na productieacceptatie van Release 7a-A.

Deze deelrelease behandelt de resterende platformhardening, SSRF-/netwerkisolatie, secretscheiding,
containerbeleid, back-upbewijs, supply-chaincontroles en de functionele privacygate.
