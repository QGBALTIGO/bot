# Seal frontend compatibility inventory

Generated from the imported upstream frontend. This is the completeness checklist for Source Baltigo compatibility.

- Pages: **19**
- React components: **23**
- Literal API endpoints discovered: **28**
- Seal branding occurrences: **8**

## Pages

- `Achievements.tsx`
- `Exchange.tsx`
- `Forbidden.tsx`
- `Gallery.tsx`
- `Hatchery.tsx`
- `Leaderboard.tsx`
- `Minigames.tsx`
- `MyPets.tsx`
- `NotFound.tsx`
- `Pass.tsx`
- `PetShop.tsx`
- `Profile.tsx`
- `Quests.tsx`
- `Referrals.tsx`
- `ServerError.tsx`
- `Shop.tsx`
- `Staff.tsx`
- `Trading.tsx`
- `Upload.tsx`

## API endpoints

- `/achievements/list` — `frontend/src/pages/Achievements.tsx`
- `/admin/rarities` — `frontend/src/components/admin/RarityEditor.tsx`
- `/admin/sudos/contributions` — `frontend/src/pages/Staff.tsx`
- `/admin/upload/options` — `frontend/src/components/character/CharActionModal.tsx`, `frontend/src/pages/Upload.tsx`
- `/battle/stats` — `frontend/src/pages/Profile.tsx`
- `/bot/info` — `frontend/src/components/Header.tsx`
- `/buy_level?levels=1` — `frontend/src/pages/Pass.tsx`
- `/claim_bank` — `frontend/src/pages/Pass.tsx`
- `/gallery` — `frontend/src/pages/Gallery.tsx`
- `/harem` — `frontend/src/pages/Profile.tsx`
- `/harem?limit=50` — `frontend/src/pages/Trading.tsx`
- `/me` — `frontend/src/context/UserContext.tsx`
- `/minigames/state` — `frontend/src/pages/Minigames.tsx`
- `/minigames/submit` — `frontend/src/pages/Minigames.tsx`
- `/pass_data` — `frontend/src/pages/Pass.tsx`
- `/quests` — `frontend/src/pages/Quests.tsx`
- `/rarities` — `frontend/src/pages/Gallery.tsx`, `frontend/src/pages/Profile.tsx`
- `/recycle` — `frontend/src/components/character/CharActionModal.tsx`
- `/recycle/preview` — `frontend/src/components/character/CharActionModal.tsx`
- `/shop/characters` — `frontend/src/pages/Shop.tsx`
- `/shop/exchange` — `frontend/src/pages/Exchange.tsx`
- `/shop/hub` — `frontend/src/pages/Shop.tsx`
- `/shop/pets` — `frontend/src/pages/PetShop.tsx`
- `/social/marriage` — `frontend/src/pages/Profile.tsx`
- `/social/referrals` — `frontend/src/pages/Referrals.tsx`
- `/social/referrals/stats` — `frontend/src/pages/Referrals.tsx`
- `/trade/offer` — `frontend/src/pages/Trading.tsx`
- `/trade/offers` — `frontend/src/pages/Trading.tsx`

## Components

- `components/Avatar.tsx`
- `components/Header.tsx`
- `components/IntroLoading.tsx`
- `components/NavigationDrawer.tsx`
- `components/admin/RarityEditor.tsx`
- `components/character/Card.tsx`
- `components/character/CharActionModal.tsx`
- `components/character/Modal.tsx`
- `components/minigames/CipherMatch.tsx`
- `components/minigames/EnergyDisplay.tsx`
- `components/minigames/NexusWheel.tsx`
- `components/minigames/RewardModal.tsx`
- `components/pet/PetActionModal.tsx`
- `components/ui/Badge.tsx`
- `components/ui/Button.tsx`
- `components/ui/Card.tsx`
- `components/ui/EmptyState.tsx`
- `components/ui/ErrorState.tsx`
- `components/ui/GachaReveal.tsx`
- `components/ui/Input.tsx`
- `components/ui/ProgressBar.tsx`
- `components/ui/Skeleton.tsx`
- `components/ui/Toast.tsx`

## Branding occurrences to adapt

- `frontend/src/utils/index.ts:38` — `"<text x='150' y='200' font-family='Arial,Helvetica,sans-serif' font-size='26' font-weight='800' fill='#2a2d3a' text-anchor='middle' letter-spacing='3'>SEAL</text>" +`
- `frontend/src/components/Header.tsx:39` — `{botName || 'SEAL'}`
- `frontend/src/components/IntroLoading.tsx:132` — `<span className="text-2xl font-black text-white tracking-[0.2em] uppercase">SEAL</span>`
- `frontend/src/components/ui/ErrorState.tsx:14` — `message = 'Could not reach the SEAL server. Check your connection and retry.',`
- `frontend/src/pages/Forbidden.tsx:31` — `This area is limited to the SEAL team.`
- `frontend/src/pages/Leaderboard.tsx:86` — `ws = new WebSocket(wsUrl, [\`seal-token.${token}\`]);`
- `frontend/src/pages/Referrals.tsx:61` — `const shareUrl = \`https://t.me/share/url?url=${encodeURIComponent(referralLink)}&text=${encodeURIComponent('Join me on SEAL — hatch and collect anime waifus. Starter perks for new `
- `frontend/src/pages/ServerError.tsx:31` — `The SEAL server hit an error. Try again in a moment.`
