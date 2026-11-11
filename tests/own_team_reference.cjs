// Request data and the same known team export for Champions Mega-Y validation.
const {Battle} = require(require('node:path').resolve(process.argv[2]));
const team = [
 {species:'Raichu', item:'Raichunite Y', ability:'Lightning Rod', nature:'Timid', evs:{spa:32,spe:32}, moves:['Fake Out','Focus Blast','Zap Cannon','Protect']},
 {species:'Gholdengo', item:'Life Orb', ability:'Good as Gold', nature:'Modest', evs:{spa:32,spe:32}, moves:['Make It Rain','Shadow Ball','Nasty Plot','Protect']},
 {species:'Arcanine', nature:'Careful', moves:['Protect']},
 {species:'Garchomp', nature:'Jolly', moves:['Protect']},
 {species:'Dragonite', nature:'Adamant', moves:['Protect']},
 {species:'Rillaboom', nature:'Adamant', moves:['Protect']},
].map(p=>({...p, level:50}));
const b=new Battle({formatid:'gen9championsvgc2026regmc',seed:[1,2,3,4]});
b.setPlayer('p1',{name:'Bot',team});b.setPlayer('p2',{name:'Opponent',team});
b.showOpenTeamSheets();
const ownSheet=b.log.find(l=>l.startsWith('|showteam|p1|'));
const request=b.p1.activeRequest;
b.choose('p1','team 1234');b.choose('p2','team 1234');
b.choose('p1','move protect mega,move protect');b.choose('p2','default');
const raichu=b.p1.active[0];
if(raichu.species.id!=='raichumegay')throw Error('Incorrect reference Mega form');
console.log(JSON.stringify({request,ownSheet,mega:{id:raichu.species.id,ability:raichu.ability,stats:raichu.storedStats}}));
