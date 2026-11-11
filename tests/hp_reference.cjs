// Emit actual Champions condition strings for the optional Python contract test.
const {Battle} = require(require('node:path').resolve(process.argv[2]));
const b = new Battle({formatid: 'gen9championsvgc2026regmc', seed: [1, 2, 3, 4]});
const team = ['Gholdengo', 'Raichu', 'Pawmot', 'Rillaboom'].map(species =>
  ({species, ability: 'No Ability', level: 50, moves: ['Protect']}));
b.setPlayer('p1', {name: 'Bot', team});
b.setPlayer('p2', {name: 'Opponent', team});
b.choose('p1', 'team 1234');
b.choose('p2', 'team 1234');
const p = b.p2.active[0];
const cases = [];
for (const [hp, maxhp, expectedHP, suffix] of [
  [50, 100, 50, 'y'], [51, 101, 50, 'g'],
  [20, 100, 20, 'r'], [41, 201, 20, 'y'],
]) {
  for (const status of ['', 'brn', 'par', 'slp', 'psn', 'tox', 'frz']) {
    p.hp = hp; p.maxhp = maxhp; p.status = status;
    const condition = p.getHealth().shared;
    if (condition !== `${expectedHP}/100${suffix}${status ? ' ' + status : ''}`) {
      throw Error(`Unexpected reference HP format: ${condition}`);
    }
    cases.push({condition, expected: [expectedHP, 100, status || null]});
  }
}
console.log(JSON.stringify(cases));
