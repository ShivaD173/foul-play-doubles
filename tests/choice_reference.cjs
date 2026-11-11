// Optional reference check: node tests/choice_reference.cjs /path/to/showdown/dist/sim
const assert = require('node:assert/strict');
const {Battle} = require(require('node:path').resolve(process.argv[2]));
function battle() {
  const b = new Battle({formatid: 'gen9championsvgc2026regmc', seed: [1, 2, 3, 4]});
  const team = [
    {species: 'Arcanine', ability: 'Intimidate', moves: ['Head Smash']},
    {species: 'Ampharos', ability: 'Static', item: 'Ampharosite', moves: ['Zap Cannon']},
    {species: 'Garchomp', ability: 'Rough Skin', moves: ['Dragon Claw']},
    {species: 'Snorlax', ability: 'Thick Fat', moves: ['Tackle']},
  ].map(p => ({...p, level: 50}));
  b.setPlayer('p1', {name: 'Bot', team});
  b.setPlayer('p2', {name: 'Opponent', team});
  b.choose('p1', 'team 1234');
  b.choose('p2', 'team 1234');
  return b;
}
const b = battle();
assert.ok(b.p1.activeRequest.active[1].canMegaEvo);
assert.equal(b.choose('p1', 'move headsmash 1,move zapcannon mega'), false);
assert.match(b.p1.choice.error, /Zap Cannon needs a target/);
assert.equal(b.choose('p1', 'move headsmash 1,move zapcannon 1 mega'), true);
assert.equal(b.p1.choice.error, '');
const fallback = battle();
assert.equal(fallback.choose('p1', 'move headsmash 1,move zapcannon mega'), false);
assert.equal(fallback.choose('p1', 'default'), true);
assert.ok(fallback.p1.isChoiceDone());
console.log('Champions choice checks passed: missing target rejected, Mega target preserved, default recovery legal.');
