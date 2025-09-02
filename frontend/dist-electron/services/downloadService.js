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
exports.setMainWindow = setMainWindow;
exports.downloadFile = downloadFile;
const https = __importStar(require("https"));
const fs = __importStar(require("fs"));
const http = __importStar(require("http"));
let mainWindow = null;
function setMainWindow(window) {
    mainWindow = window;
}
function downloadFile(url, outputPath) {
    return new Promise((resolve, reject) => {
        console.log(`开始下载文件: ${url}`);
        console.log(`保存路径: ${outputPath}`);
        const file = fs.createWriteStream(outputPath);
        // 创建HTTP客户端，兼容https和http
        const client = url.startsWith('https') ? https : http;
        client
            .get(url, response => {
            const totalSize = parseInt(response.headers['content-length'] || '0', 10);
            let downloadedSize = 0;
            console.log(`文件大小: ${totalSize} bytes`);
            response.pipe(file);
            response.on('data', chunk => {
                downloadedSize += chunk.length;
                const progress = totalSize ? Math.round((downloadedSize / totalSize) * 100) : 0;
                console.log(`下载进度: ${progress}% (${downloadedSize}/${totalSize})`);
                if (mainWindow) {
                    mainWindow.webContents.send('download-progress', {
                        progress,
                        status: 'downloading',
                        message: `下载中... ${progress}%`,
                    });
                }
            });
            file.on('finish', () => {
                file.close();
                console.log(`文件下载完成: ${outputPath}`);
                resolve();
            });
            file.on('error', err => {
                console.error(`文件写入错误: ${err.message}`);
                fs.unlink(outputPath, () => { }); // 删除不完整的文件
                reject(err);
            });
        })
            .on('error', err => {
            console.error(`下载错误: ${err.message}`);
            reject(err);
        });
    });
}
