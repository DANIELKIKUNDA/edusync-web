# Revue de pré-staging — chaîne d'approvisionnement

Date : 2026-10-16. Périmètre : les 2 paquets classés « à examiner » par `tools/certification/supply_chain.py` lors de
la certification N3 (manifeste sur `cc03eb5`, tag `n3-local-certified-2026-10-16`). **Aucune dépendance modifiée.**
Ce document est une analyse technique, pas un avis juridique.

## 1. Source

`certification/n0-n1-20261007/supply-chain.json`, champ `summary.flagged` :

| Paquet | Version | Licence déclarée | Classement |
|---|---|---|---|
| `psycopg` | 3.3.5 | `LGPL-3.0-only` | `LGPL_LIAISON_DYNAMIQUE` |
| `psycopg-binary` | 3.3.5 | `LGPL-3.0-only` | `LGPL_LIAISON_DYNAMIQUE` |

Les autres paquets sont permissifs : 44 paquets Python sur 46 et les 73 paquets npm livrés au navigateur. Aucun
paquet sous GPL, AGPL ou SSPL, et aucune licence inconnue.

**Raison exacte du classement.** La fonction `classify()` du script ne range jamais une licence contenant `LGPL`
dans `PERMISSIVE`. Elle la place dans une classe à part, `LGPL_LIAISON_DYNAMIQUE`, qui est comptée comme « à
examiner ». C'est un signalement volontaire de la catégorie de licence, pas la détection d'un problème. La licence
est lue dans la métadonnée `License-Expression` des paquets installés.

## 2. Fiches

### 2.1 `psycopg` 3.3.5

| Critère | Constat |
|---|---|
| Écosystème | Python (PyPI) |
| Directe / transitive | **Directe** : `backend/pyproject.toml` déclare `"psycopg[binary]>=3.2"`, version figée dans `backend/requirements.lock` (`psycopg==3.3.5`) |
| Runtime / développement | **Runtime** : installé dans l'image de production (`backend/Dockerfile` : `pip install -c requirements.lock .`) |
| Licence | LGPL-3.0-only (fichier `psycopg-3.3.5.dist-info/licenses/LICENSE.txt` fourni dans la roue) |
| Utilisation réelle | Pilote PostgreSQL de toute l'application. SQLAlchemy l'utilise via les URL `postgresql+psycopg://…` pour l'API, les workers, le migrateur et l'outil de sauvegarde. Deux adaptateurs l'importent directement (`from psycopg.rows import dict_row` dans `postgres_fee_tracking.py` et `postgres_finance_recovery.py`). Aucune modification du code source de psycopg. |
| Obligations | La LGPL-3.0 ne s'applique qu'en cas de **distribution** (« convey ») de la bibliothèque. Un SaaS dont le code tourne sur nos serveurs ne distribue rien : la LGPL n'a pas la clause réseau de l'AGPL. En cas de distribution (image Docker remise à une école, installation sur site) : fournir le texte de la licence et un accès au code source de psycopg (pas d'EduSync), et laisser l'utilisateur remplacer la bibliothèque. Cette dernière condition est remplie de fait, puisque psycopg est un module Python séparé chargé dynamiquement. |
| Risque SaaS commercial | **Faible.** Utilisation non modifiée, chargement dynamique, pas de distribution en mode SaaS. Le code propriétaire d'EduSync n'est pas contaminé par la LGPL. |
| Alternative | Aucune sans changement profond : psycopg2 est aussi sous LGPL ; `asyncpg` (Apache-2.0) n'est pas un pilote synchrone compatible avec le code actuel ; `pg8000` (BSD) est plus lent et non certifié. Remplacer le pilote demanderait de recertifier N0 à N3. |
| **Recommandation** | **`KEEP`** |

### 2.2 `psycopg-binary` 3.3.5

| Critère | Constat |
|---|---|
| Écosystème | Python (PyPI), roue binaire compilée |
| Directe / transitive | **Transitive** : tirée par l'extra `[binary]` de la dépendance directe `psycopg[binary]`. Version figée dans `requirements.lock`. |
| Runtime / développement | **Runtime** : installée dans l'image de production. psycopg charge automatiquement l'implémentation C quand elle est présente, avec repli sur l'implémentation Python pure. |
| Licence | LGPL-3.0-only pour le code psycopg. La roue **embarque aussi des bibliothèques tierces**. Sur la roue Windows de l'environnement certifié, on trouve `libpq` (licence PostgreSQL, permissive), `libssl` et `libcrypto` (OpenSSL 3, Apache-2.0). La roue Linux (`manylinux`) utilisée par l'image `python:3.12-slim` embarque aussi libpq, OpenSSL et peut-être d'autres bibliothèques système (Kerberos, LDAP, SASL…). Cette liste n'a pas été vérifiée ici, car l'image Linux n'a pas été construite pendant cette revue. |
| Raison du classement | Même règle que ci-dessus. Le script ne lit pas les licences des bibliothèques embarquées. |
| Utilisation réelle | Accélération C du pilote : connexion libpq, conversions, COPY. Aucun appel direct depuis le code EduSync. |
| Obligations | Mêmes obligations LGPL que `psycopg`, uniquement en cas de distribution. S'y ajoutent les mentions des bibliothèques embarquées : avis OpenSSL et Apache-2.0, licence PostgreSQL. Ces textes accompagnent déjà la roue. En SaaS, aucune obligation de redistribution. |
| Risque SaaS commercial | **Faible** pour la licence. Le seul risque opérationnel est la **sécurité** : OpenSSL et libpq sont figés dans la roue et ne suivent pas les mises à jour du système. Un correctif OpenSSL impose donc de monter la version de psycopg-binary. |
| Alternative | Remplacer `psycopg[binary]` par `psycopg[c]` (compilé contre la libpq et l'OpenSSL du système, mis à jour par l'image de base) ou par psycopg en Python pur avec la `libpq5` de Debian. La licence reste la même (LGPL) et seul le mode de mise à jour d'OpenSSL change. C'est une décision d'exploitation, pas une obligation, et elle demanderait une nouvelle certification : ne pas la faire avant le staging. |
| **Recommandation** | **`KEEP`**, avec une surveillance des avis de sécurité OpenSSL et libpq (voir § 3) |

## 3. Conclusion et actions proposées (aucune exécutée)

1. **`KEEP` pour les deux paquets.** Aucun `REPLACE`, `REMOVE` ou `LEGAL_REVIEW` n'est justifié pour un SaaS.
2. Un **`LEGAL_REVIEW` deviendrait nécessaire** seulement si EduSync était un jour **distribué** : image Docker remise
   à un client, installation sur site ou application de bureau embarquant psycopg. Il faudrait alors livrer les textes
   de licence (LGPL-3.0, OpenSSL et Apache-2.0, PostgreSQL) et un lien vers le code source de psycopg 3.3.5.
3. Ajouter au fichier d'attributions (« Licences tierces »), au moment du staging, la mention de psycopg (LGPL-3.0)
   et des bibliothèques embarquées. Ce n'est pas obligatoire en SaaS, mais c'est une bonne pratique peu coûteuse.
4. Surveiller les correctifs de sécurité de psycopg-binary : un correctif OpenSSL ou libpq impose une montée de
   version, suivie d'une nouvelle passe de certification. `pip-audit` n'a pas tourné pendant la certification
   locale, faute de réseau. Il est à exécuter en staging (voir `STAGING_READINESS.md`).
5. Le script `supply_chain.py` lit les licences dans l'environnement Windows (roues `cp313-win_amd64`), alors que
   l'image de production installe des roues Linux pour Python 3.12. Il faut régénérer le SBOM **depuis l'image
   construite**, pour qu'il décrive exactement ce qui sera déployé.
