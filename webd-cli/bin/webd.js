#!/usr/bin/env node


const installNode = require("../commands/install-node");
const installPool = require("../commands/install-pool");
const startNode = require("../commands/start-node");
const startPool = require("../commands/start-pool");
const dockerNode = require("../commands/docker-node");

const [,, cmd, subcmd] = process.argv;


if (cmd === "install" && subcmd === "node") {
	installNode();
} else if (cmd === "install" && subcmd === "pool") {
	installPool();
} else if (cmd === "start" && subcmd === "node") {
	startNode();
} else if (cmd === "start" && subcmd === "pool") {
	startPool();
} else if (cmd === "docker" && subcmd === "node") {
	dockerNode();
} else {
	console.log("WebDollar 2026 CLI – ready to install node or pool.");
	console.log("Comenzi disponibile:");
	console.log("  webd install node");
	console.log("  webd install pool");
	console.log("  webd start node");
	console.log("  webd start pool");
	console.log("  webd docker node");
}
