# KickrVent voor Home Assistant

Eigen, lokale **alleen-lezen** integratie voor een wifi-KICKR via WFTNP/DIRCON. Ontwikkelversie 0.1.1. Het is een nieuwe implementatie op basis van de protocolbeschrijving en onze TS-PoC, geen fork van `hacs-wahoo-wftnp`.

## Installatie

1. Pak `artifacts/kickrvent-0.1.1.zip` uit in de configuratiemap van Home Assistant. Het resultaat moet **`config/custom_components/kickrvent/manifest.json`** zijn. Geen extra tussenmap `KickrVent` of `custom_components/custom_components`.
2. Herstart Home Assistant om de nieuwe integratie te laden.
3. Ga naar **Instellingen → Apparaten & diensten → Integratie toevoegen → KickrVent**, of gebruik de automatisch ontdekte trainer.
4. Kies je trainer uit de lijst na de automatische netwerkscan. Adres, poort en serienummer worden overgenomen. Je kunt ook opnieuw zoeken of handmatig een adres invoeren. De standaardpoort is **36866**.
5. Het serienummer wordt bij voorkeur uit de trainer gelezen. Als de trainer dit niet levert, gebruik het serienummer op het label (of de mDNS-advertentie) in het optionele veld. Dit vormt de blijvende identiteit; verander het niet wanneer alleen het IP-adres wijzigt.

Zet voor de eerste test de bestaande Wahoo-integratie uit en stop eventuele verbindingen vanuit de TS-PoC. Test vervolgens opnieuw met ROUVY actief. 

De integratie is beschikbaar als [HACS custom repository](https://github.com/mightymax/hacs-kickrvent). Zie de README voor de installatieknoppen. De release-ZIP is bedoeld voor handmatig uitpakken in de HA-configuratiemap. HACS installeert de component rechtstreeks uit de Git-tag.

## Entiteiten

Alle entiteiten horen bij één apparaat met het serienummer als vaste identiteit. HA kiest de concrete entity-ID's op basis van taal, apparaatnaam en eventuele bestaande namen.

| Entiteit | Gedrag |
| --- | --- |
| Snelheid | km/u, afgerond op 0,1; trainer-/vliegwielsnelheid, geen virtuele ROUVY-snelheid |
| Vermogen | watt, afgerond op gehele waarden |
| Cadans | rpm, afgerond op 0,1 |
| Verbinding | Diagnostische binaire sensor voor een actieve, geïnitialiseerde TCP-sessie |
| Activiteit | Positieve snelheid, vermogen of cadans ontvangen binnen de activiteitstimeout; onbeschikbaar bij ontbrekende/verouderde meetdata |

Als FTMS Indoor Bike Data ontbreekt, maar Cycling Power wel beschikbaar is, wordt alleen vermogen geleverd. Snelheid en cadans blijven dan onbeschikbaar; ze worden niet geschat. Onbeschikbaar is nooit hetzelfde als gemeten nul.

## Bescherming tegen databasegroei

- Meldingen van de trainer overschrijven een buffer met hoogstens drie meetvelden. Er is geen onbegrensde wachtrij of taak per melding.
- Gewijzigde meetwaarden worden standaard maximaal eens per **5 seconden** naar de coordinator gepubliceerd. Bij verbindingsverlies of het verlopen van gegevens worden oude waarden meteen ongeldig gemaakt.
- `always_update=False`, vergelijkbare momentopnamen en normale HA-entiteiten zonder `force_update` voorkomen ongewijzigde state-updates.
- Geen `last_seen`-sensor of voortdurend wijzigende tijdstempel-attributen. Idle nulmetingen blijven intern verwerkt, zonder nieuwe publicaties zolang de toestand gelijk blijft.
- Activiteit wordt na standaard **15 seconden** zonder positieve meting uitgeschakeld. Nieuwe meetdata blijft gewoon binnenkomen; de verbinding wordt niet verbroken wegens stilstand.
- Iedere meetwaarde wordt afzonderlijk na standaard **30 seconden** zonder verversing onbeschikbaar. Andere, nog verse velden blijven beschikbaar.

Tijdens fietsen kunnen veranderende metingen nog steeds in Recorder en langetermijnstatistieken terechtkomen. Het is dus geen garantie op nul databasegroei. Verhoog het publicatie-interval als minder historie gewenst is; bestaande Recorder-instellingen worden niet gewijzigd.

## Verbinding en herstel

- Eén reader en één geserialiseerde request tegelijk per verbinding.
- Requests en verbinden hebben een timeout van 5 seconden; frames hebben een maximum van 8192 bytes.
- Iedere 20 seconden controle via read-only service discovery, ook als de trainer geen notificaties stuurt.
- Een verbroken verbinding wordt opgeruimd. Herhaalpogingen met oplopende wachttijd van 2 tot maximaal 60 seconden plus kleine willekeurige spreiding voorkomen drukke retry-lussen.
- Bij uitval worden meetwaarden gewist. Na herverbinden moet elk veld opnieuw worden ontvangen.
- Eén waarschuwing per ononderbroken uitval; overige mislukte pogingen op debugniveau.
- Bij verwijderen/herladen worden de taken en socket gesloten.
- Herconfigureren via het menu van de integratie kan host en poort wijzigen zonder nieuwe apparaatidentiteit. mDNS kan een gewijzigd adres van een al bekend serienummer bijwerken.

Deze integratie vraagt **geen FTMS-control** en verstuurt geen characteristic writes (DIRCON type 4). ROUVY kan de weerstand blijven regelen voor zover de trainer gelijktijdige netwerkverbindingen toestaat. Dat laatste is nog niet op echte hardware bevestigd.

## Opties

| Instelling | Standaard | Grenzen |
| --- | --- | --- |
| Publicatie-interval | 5 s | 2–60 s |
| Geldigheid meetgegevens | 30 s | 15–300 s |
| Activiteitstimeout | 15 s | 5–120 s |

Opties zijn via de HA-interface aanpasbaar; opslaan herlaadt deze integratie en verbindt opnieuw.

## Ventilator koppelen

Gebruik later de vermogens- of activiteitssensor als bron voor een gewone HA-automatisering. De huidige slimme stekker kan aan/uit worden geschakeld; een ondersteunde regelbare ventilator kan een percentage krijgen. De integratie zelf verandert geen ventilatorinstellingen en maakt geen automatisering aan. Laat een automatisering `unavailable` expliciet afhandelen, zodat oude trainingsdata niet blijft doorwerken.

## Ontwikkelen en testen

Vanaf de repositorymap, met `uv`:

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python \
  --override test-overrides.txt -r requirements-test.txt
.venv/bin/pytest tests -q
python3 scripts/package_ha.py
```

De override betreft alleen de lokale testomgeving: HA's gepinde `lru-dict` 1.3.0 bouwde niet met de lokale macOS-toolchain. De component zelf installeert geen extra Python-dependencies en wijzigt geen HA-runtimepackages.

Regressietests gebruiken een echte HA-testomgeving en een lokale TCP-trainer. Ze controleren configuratie, dubbele apparaten, IP-wijziging, opties, verkeerde serienummers, notificaties, fragmentatie, timeouts, alleen-lezen gedrag, veldveroudering, reconnect, unload en een gesimuleerde dag stilstand. Een fysieke KICKR v6 is bereikbaar gebleken met de Python-client; er zijn geldige FTMS-nulmetingen ontvangen tijdens stilstand. Dit bevestigt nog geen metingen tijdens fietsen, een langdurige Recorder-meting of gelijktijdig gebruik naast ROUVY.

Ondergrens voor deze ontwikkelversie: Home Assistant 2026.2. De testmatrix bevat HA 2026.2.3/Python 3.13 en HA 2026.10.4/Python 3.14.

## Bronnen

- [WFTNP/DIRCON-protocolbeschrijving](https://github.com/elfrances/wahoo-fitness-tnp)
- [Ervaringen met databasegroei en verbindingen in de andere integratie](https://github.com/kilianyp/hacs-wahoo-wftnp/issues/2)
- [HA-coordinator en updates zonder wijzigingen overslaan](https://developers.home-assistant.io/docs/integration_fetching_data/)
