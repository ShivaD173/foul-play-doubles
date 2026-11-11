// Optional reference check: node tests/choice_reference.cjs /path/to/showdown/dist/sim
const assert = require('node:assert/strict');
const {Battle} = require(require('node:path').resolve(process.argv[2]));
function battle() {
  const b = new Battle({formatid: 'gen9championsvgc2026regmc', seed: [1, 2, 3, 4]});
  const team = [
    {species: 'Arcanine', ability: 'Intimidate', moves: ['Head Smash']},
    {species: 'Ampharos', ability: 'Static', item: 'Ampharosite', moves: ['Zap Cannon']},
    {species: 'Garchomp', ability: 'Rough Skin', item: 'Garchompite', moves: ['Dragon Claw']},
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

// Once one teammate has Mega Evolved, another holder's request must forbid it.
const used = battle();
for (const side of used.sides) {
  for (const p of side.pokemon) p.hp = p.maxhp = p.baseMaxhp = 5000;
}
assert.equal(used.choose('p1', 'move headsmash 1,move zapcannon 1 mega'), true);
assert.equal(used.choose('p2', 'default'), true);
assert.equal(used.choose('p1', 'switch 3,move zapcannon 1'), true);
assert.equal(used.choose('p2', 'default'), true);
assert.equal(used.p1.active[0].species.id, 'garchomp');
assert.ok(!used.p1.activeRequest.active[0].canMegaEvo);
assert.equal(used.choose('p1', 'move dragonclaw 1 mega,move zapcannon 1'), false);
assert.match(used.p1.choice.error, /can't mega evolve/);
assert.equal(used.choose('p1', 'move dragonclaw 1,move zapcannon 1'), true);
console.log('Champions Mega resource check passed: another stone holder cannot Mega after its teammate.');
