// Emit the actual Champions open-team-sheet protocol, excluding hidden EVs/IVs.
const {Battle} = require(require('node:path').resolve(process.argv[2]));
const b = new Battle({formatid: 'gen9championsvgc2026regmc', seed: [1, 2, 3, 4]});
const team = [
  {species: 'Gholdengo', nature: 'Modest', item: 'Life Orb', ability: 'Good as Gold', moves: ['Make It Rain', 'Shadow Ball', 'Nasty Plot', 'Protect']},
  {species: 'Raichu', nature: 'Timid', item: 'Focus Sash', ability: 'Lightning Rod', moves: ['Fake Out', 'Zap Cannon', 'Focus Blast', 'Protect']},
  {species: 'Pawmot', nature: 'Jolly', item: 'Sitrus Berry', ability: 'Iron Fist', moves: ['Revival Blessing', 'Double Shock', 'Close Combat', 'Fake Out']},
  {species: 'Rillaboom', nature: 'Adamant', item: 'Miracle Seed', ability: 'Grassy Surge', moves: ['Fake Out', 'Wood Hammer', 'Grassy Glide', 'Protect']},
  {species: 'Garchomp', nature: 'Jolly', item: 'Garchompite', ability: 'Rough Skin', moves: ['Earthquake', 'Dragon Claw', 'Rock Slide', 'Protect']},
  {species: 'Dragonite', nature: 'Adamant', item: 'Leftovers', ability: 'Multiscale', moves: ['Extreme Speed', 'Dragon Claw', 'Ice Spinner', 'Protect']},
].map(p => ({...p, level: 50, evs: {atk: 252, hp: 252, spe: 4}, ivs: {atk: 0, spe: 0}}));
b.setPlayer('p1', {name: 'Bot', team});
b.setPlayer('p2', {name: 'Opponent', team});
b.showOpenTeamSheets();
const line = b.log.find(line => line.startsWith('|showteam|p2|'));
if (!line) throw Error('Missing reference open sheet');
console.log(JSON.stringify({line, expected: team}));
