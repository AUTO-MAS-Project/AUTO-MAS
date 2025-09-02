"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.getAppRoot = getAppRoot;
exports.checkEnvironment = checkEnvironment;
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const electron_1 = require("electron");
// 获取应用根目录
function getAppRoot() {
    return process.env.NODE_ENV === 'development' ? process.cwd() : path.dirname(electron_1.app.getPath('exe'));
}
// 检查环境
function checkEnvironment(appRoot) {
    const environmentPath = path.join(appRoot, 'environment');
    const pythonPath = path.join(environmentPath, 'python');
    const gitPath = path.join(environmentPath, 'git');
    const backendPath = path.join(appRoot, 'backend');
    const requirementsPath = path.join(backendPath, 'requirements.txt');
    const pythonExists = fs.existsSync(pythonPath);
    const gitExists = fs.existsSync(gitPath);
    const backendExists = fs.existsSync(backendPath);
    // 检查依赖是否已安装（简单检查是否存在site-packages目录）
    const sitePackagesPath = path.join(pythonPath, 'Lib', 'site-packages');
    const dependenciesInstalled = fs.existsSync(sitePackagesPath) && fs.readdirSync(sitePackagesPath).length > 10;
    return {
        pythonExists,
        gitExists,
        backendExists,
        dependenciesInstalled,
        isInitialized: pythonExists && gitExists && backendExists && dependenciesInstalled,
    };
}
