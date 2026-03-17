#!/usr/bin/env node

import axios from 'axios';
import readline from 'readline';
import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';
import dotenv from 'dotenv';
import chalk from 'chalk';
import { marked } from 'marked';
import TerminalRenderer from 'marked-terminal';
import boxen from 'boxen';
import ora from 'ora';

dotenv.config();

marked.setOptions({
    renderer: new TerminalRenderer({
        codespan: chalk.yellow,
        code: chalk.greenBright,
        heading: chalk.bold.cyan,
        listitem: chalk.white
    })
});

const API_URL = process.env.BACKEND_URL || "http://localhost:8000/chat";

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

let messages = [];

console.log(chalk.cyan.bold("\n--- Rathi CLI (Codex Style) ---"));
console.log(chalk.dim(`Connecting to: ${API_URL}\n`));

function askPrompt() {
    rl.question(chalk.blue.bold("\n> "), async (input) => {
        const trimmed = input.trim();
        if (!trimmed) {
             askPrompt();
             return;
        }

        if (trimmed.toLowerCase() === "\\exit" || trimmed.toLowerCase() === "/exit") {
            console.log(chalk.yellow("Goodbye!"));
            rl.close();
            return;
        }

        messages.push({ role: "user", content: trimmed });
        await runConversationLoop();
        askPrompt();
    });
}

async function runConversationLoop() {
     const spinner = ora(chalk.cyan("Thinking...")).start();
     
     while (true) {
         try {
             const response = await axios.post(API_URL, {
                 messages: messages,
                 model: process.env.DEFAULT_MODEL || "nvidia/nemotron-3-super-120b-a12b:free"
             });

             spinner.stop();

             const data = response.data;
             if (!data.ok) {
                  console.error(chalk.red("\nBackend Error:"), data.detail);
                  break;
             }

             const content = data.content;
             const reasoning = data.reasoning;

             // Display reasoning if present
             if (reasoning) {
                  console.log(boxen(chalk.gray(reasoning), {
                       title: "Reasoning",
                       borderColor: "gray",
                       padding: 1,
                       margin: 1,
                       borderStyle: "round"
                  }));
             }

             // Check for Tool Call tags
             const toolCallMatch = content.match(/<tool_call>\s*(\{.*?\})\s*<\/tool_call>/s);
             
             if (toolCallMatch) {
                  const rawJson = toolCallMatch[1];
                  try {
                       const toolCall = JSON.parse(rawJson);
                       console.log(chalk.magenta(`\n⚙️  [Tool Triggered]: ${toolCall.action}`));
                       const result = await executeLocalTool(toolCall);
                       
                       messages.push({ role: "assistant", content: content });
                       messages.push({ role: "user", content: `TOOL RESULT\n${JSON.stringify(result)}` });
                       
                       spinner.text = chalk.cyan(`Returning ${toolCall.action} output...`);
                       spinner.start();
                       continue; 
                  } catch (e) {
                       console.error(chalk.red("\nError parsing tool JSON:"), e.message);
                       break;
                  }
             } else {
                  // Render using Marked and Boxen for rich display
                  const rendered = marked(content);
                  console.log(boxen(rendered, {
                       title: chalk.greenBright("Assistant"),
                       borderColor: "green",
                       padding: 1,
                       margin: 1,
                       borderStyle: "round"
                  }));
                  
                  messages.push({ role: "assistant", content: content });
                  break;
             }

         } catch (e) {
              spinner.stop();
              console.error(chalk.red("\nRequest Failed:"), e.message);
              break;
         }
     }
}

async function executeLocalTool(toolCall) {
    const workspaceRoot = process.cwd();

    try {
        if (action === "list_dir") {
            const tgt = path.join(workspaceRoot, toolCall.path || ".");
            const files = fs.readdirSync(tgt);
            return { ok: true, action: "list_dir", entries: files.map(f => ({ name: f })) };
        }
        else if (action === "read_file") {
            const tgt = path.join(workspaceRoot, toolCall.path);
            const content = fs.readFileSync(tgt, 'utf-8');
            return { ok: true, action: "read_file", content: content };
        }
        else if (action === "write_file") {
            const tgt = path.join(workspaceRoot, toolCall.path);
            fs.writeFileSync(tgt, toolCall.content, 'utf-8');
            return { ok: true, action: "write_file", path: toolCall.path, bytes_written: toolCall.content.length };
        }
        else if (action === "run_command") {
            return new Promise((resolve) => {
                exec(toolCall.command, { cwd: workspaceRoot }, (error, stdout, stderr) => {
                    resolve({
                        ok: true,
                        action: "run_command",
                        exit_code: error ? error.code : 0,
                        stdout: stdout,
                        stderr: stderr
                    });
                });
            });
        }
        else {
             return { ok: false, error: `Tool call ${action} not supported locally on node driver yet.` };
        }
    } catch (e) {
        return { ok: false, action: toolCall.action, error: e.message };
    }
}

askPrompt();
