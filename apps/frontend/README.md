# Frontend

**Tech :** Vue 3 + WXT (TypeScript, Tailwind). Playwright pour les tests E2E.

**Code Guidelines :** Extension pour Google Chrome et Microsoft Edge respectant le Manifest V3. Utilisation du "Shadow DOM" pour isoler les styles CSS. Les tests E2E automatisés via Playwright (situés dans le sous-dossier e2e-tests) doivent simuler le parcours utilisateur téléchargeant différents fichiers sur le webmail.

**Contexte Métier :** Interface de l'utilisateur final. Doit gérer les états visuels : Vert (Autorisé), Rouge (Bloqué), Orange (Avertissement avec panneau latéral).

**Responsabilité :** Intercepter automatiquement le clic de téléchargement via les content scripts.

**Événements Kafka (Consommés/Produits) :** N/A (Communique via API REST/WebSockets avec le Backend).
