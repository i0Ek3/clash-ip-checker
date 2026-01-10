/**
 * Clash IP Checker - Alpine.js Application
 */

function app() {
    return {
        // State
        yamlContent: '',
        config: {
            // 核心配置
            fast_mode: true,
            clash_api_url: 'http://127.0.0.1:9097',
            clash_api_secret: '',
            // 可选配置
            source: 'ping0',
            fallback: true,
            output_suffix: '_checked',
            selector_name: 'GLOBAL',
            headless: true,
            // 跳过关键词 (逗号分隔字符串)
            skip_keywords_str: '剩余,重置,到期,有效期,官网,网址,更新,公告,建议'
        },
        isRunning: false,
        showProgress: false,
        progress: 0,
        total: 0,
        currentNode: '',
        nodes: [],
        selected: [],
        error: '',

        // Edit state
        editingId: null,
        editValue: '',

        // Export state
        exportedYaml: '',
        exportFilename: '',
        exportUrl: '',

        // CodeMirror editor instance
        editor: null,
        exportEditor: null,
        eventSource: null,  // SSE connection reference

        // Initialize CodeMirror (only once)
        init() {
            // Prevent double initialization
            if (this.editor) return;

            const container = document.getElementById('yaml-editor');
            if (!container || container.querySelector('.CodeMirror')) return;

            this.editor = CodeMirror(container, {
                mode: 'yaml',
                theme: 'material-darker',
                lineNumbers: true,
                lineWrapping: false,
                placeholder: 'proxies:\n  - name: HK 01\n    type: ss\n    server: example.com\n    ...'
            });

            // Sync editor content to yamlContent and scroll to top after paste
            this.editor.on('change', (cm, change) => {
                this.yamlContent = this.editor.getValue();
                // Scroll to first line after paste operation (delay to ensure it happens after render)
                if (change.origin === 'paste' || change.origin === 'setValue') {
                    setTimeout(() => {
                        cm.scrollTo(0, 0);
                        cm.setCursor(0, 0);
                    }, 10);
                }
            });

            // Cleanup SSE on page unload to prevent connection leaks
            window.addEventListener('beforeunload', () => {
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
            });
        },

        isRechecking: false,  // Exclusive lock for recheck

        // Methods
        async startCheck() {
            this.error = '';
            this.progress = 0;
            this.isRechecking = false;

            try {
                // Validate first
                const validateRes = await fetch('/api/validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ yaml_content: this.yamlContent })
                });

                const validateData = await validateRes.json();
                if (!validateData.valid) {
                    this.error = validateData.error;
                    return;
                }

                // Start check
                const startRes = await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        yaml_content: this.yamlContent,
                        config: this.config
                    })
                });

                if (!startRes.ok) {
                    if (startRes.status === 409) {
                        // Task is already running, just reconnect to SSE
                        this.isRunning = true;
                        this.showProgress = true;
                        this.connectSSE();
                        return;
                    }
                    const err = await startRes.json();
                    this.error = err.detail;
                    setTimeout(() => { this.error = null; }, 3000);
                    return;
                }

                const startData = await startRes.json();

                // Reset State for new run
                this.progress = 0;
                this.error = null;
                this.total = startData.total;

                this.isRunning = true;
                this.showProgress = true;

                // Fetch initial nodes (pending state) immediately
                try {
                    const nodesRes = await fetch('/api/nodes');
                    const nodesData = await nodesRes.json();
                    this.nodes = nodesData.nodes;
                    this.selected = this.nodes.map(n => n.id); // Default select all
                } catch (e) {
                    console.error("Initial nodes fetch failed", e);
                    this.nodes = [];
                    this.selected = [];
                }

                // Connect SSE
                this.connectSSE();

            } catch (e) {
                this.error = `请求失败: ${e.message}`;
            }
        },

        connectSSE() {
            // Close existing connection if any
            if (this.eventSource) {
                this.eventSource.close();
            }

            this.eventSource = new EventSource('/api/progress');

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);

                if (data.type === 'progress') {
                    this.progress = data.progress;
                    this.currentNode = data.node?.original_name || '';
                    if (data.node) {
                        const idx = this.nodes.findIndex(n => n.id === data.node.id);
                        if (idx !== -1) {
                            this.nodes[idx] = data.node;
                        } else {
                            this.nodes.push(data.node);
                            this.selected.push(data.node.id);
                        }
                    }
                } else if (data.type === 'update') {
                    // Handle single node update
                    const idx = this.nodes.findIndex(n => n.id === data.node.id);
                    if (idx !== -1) {
                        this.nodes.splice(idx, 1, data.node);
                    }
                } else if (data.type === 'complete') {
                    this.isRunning = false;
                    this.currentNode = '';
                    this.eventSource.close();
                    this.eventSource = null;
                } else if (data.type === 'stopped') {
                    this.isRunning = false;
                    this.currentNode = '已停止';
                    this.eventSource.close();
                    this.eventSource = null;
                } else if (data.type === 'error') {
                    console.error('Node error:', data);
                }
            };

            this.eventSource.onerror = () => {
                if (!this.isRunning && this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
            };
        },

        async recheckNode(node) {
            if (this.isRunning || this.isRechecking) return;

            this.isRechecking = true;
            const originalName = node.name;
            node.name = "⏳ 检测中..."; // Visual feedback

            try {
                const res = await fetch(`/api/nodes/${node.id}/recheck`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        config: this.config
                    })
                });

                if (!res.ok) {
                    const data = await res.json();
                    const errMsg = typeof data.detail === 'object' ? JSON.stringify(data.detail) : (data.detail || '重测失败');
                    alert(errMsg);
                    // Revert name on failure if not updated via SSE/Response
                    const idx = this.nodes.findIndex(n => n.id === node.id);
                    if (idx !== -1) this.nodes[idx].name = originalName;
                } else {
                    const data = await res.json();
                    const idx = this.nodes.findIndex(n => n.id === data.node.id);
                    if (idx !== -1) {
                        this.nodes.splice(idx, 1, data.node);
                    }
                }

            } catch (e) {
                alert('请求失败: ' + e);
                const idx = this.nodes.findIndex(n => n.id === node.id);
                if (idx !== -1) this.nodes[idx].name = originalName;
            } finally {
                this.isRechecking = false;
            }
        },

        async stopCheck() {
            try {
                await fetch('/api/stop', { method: 'POST' });
                this.isRunning = false;
            } catch (e) {
                console.error('Stop failed:', e);
            }
        },

        // Selection
        selectAll() {
            this.selected = this.nodes.map(n => n.id);
        },

        selectNone() {
            this.selected = [];
        },

        toggleAll(e) {
            if (e.target.checked) {
                this.selectAll();
            } else {
                this.selectNone();
            }
        },

        // Edit
        startEdit(node) {
            this.editingId = node.id;
            this.editValue = node.name;
            this.$nextTick(() => {
                const input = document.querySelector('.inline-edit');
                if (input) input.focus();
            });
        },

        async saveEdit(node) {
            if (this.editValue.trim() && this.editValue !== node.name) {
                try {
                    await fetch(`/api/nodes/${node.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: this.editValue })
                    });
                    node.name = this.editValue;
                } catch (e) {
                    console.error('Save failed:', e);
                }
            }
            this.editingId = null;
        },

        cancelEdit() {
            this.editingId = null;
        },

        // Delete
        async deleteNode(node) {
            if (!confirm(`确定删除节点 "${node.original_name}"?`)) return;

            try {
                await fetch(`/api/nodes/${node.id}`, { method: 'DELETE' });
                this.nodes = this.nodes.filter(n => n.id !== node.id);
                this.selected = this.selected.filter(id => id !== node.id);
            } catch (e) {
                console.error('Delete failed:', e);
            }
        },

        // Risk color class based on percentage (Matches Python get_emoji logic)
        getRiskClass(risk) {
            if (!risk || risk === '❓' || risk === 'N/A') return '';
            const num = parseInt(risk);
            if (isNaN(num)) return '';

            if (num <= 10) return 'risk-white';
            if (num <= 30) return 'risk-green';
            if (num <= 50) return 'risk-yellow';
            if (num <= 70) return 'risk-orange';
            if (num <= 90) return 'risk-red';
            return 'risk-black';
        },

        // Shared users color class (Matches Python logic: <=10, <=100, <=1000, <=10000, >10000)
        getSharedClass(shared) {
            if (!shared || shared === 'N/A' || shared === '❓') return '';

            // Extract numbers from string (e.g. "100-500" -> [100, 500])
            const nums = String(shared).match(/\d+/g);
            if (!nums || nums.length === 0) return '';

            // Use the upper bound (last number) logic
            let upper = parseInt(nums[nums.length - 1]);

            // If contains '+', increment to push to next category (e.g. 10000+ -> 10001 -> Black)
            if (String(shared).includes('+')) {
                upper += 1;
            }

            if (upper <= 10) return 'shared-green';
            if (upper <= 100) return 'shared-yellow';
            if (upper <= 1000) return 'shared-orange';
            if (upper <= 10000) return 'shared-red';
            return 'shared-black';
        },

        // Export
        async exportYaml() {
            if (this.selected.length === 0) {
                alert('请先选择要导出的节点');
                return;
            }

            try {
                const res = await fetch('/api/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ node_ids: this.selected })
                });

                const data = await res.json();
                this.exportedYaml = data.yaml;
                this.exportFilename = data.filename;
                this.exportUrl = data.url;
                this.$refs.exportModal.showModal();

                // Initialize Export Editor
                this.$nextTick(() => {
                    const el = document.getElementById('export-editor');
                    if (!el) return;

                    // Clear and recreate to avoid stale content
                    el.innerHTML = '';
                    this.exportEditor = CodeMirror(el, {
                        mode: 'yaml',
                        theme: 'material-darker',
                        lineNumbers: true,
                        readOnly: true,
                        lineWrapping: true,
                        value: this.exportedYaml
                    });
                    setTimeout(() => this.exportEditor.refresh(), 50);
                });

            } catch (e) {
                alert(`导出失败: ${e.message}`);
            }
        },

        downloadYaml() {
            const blob = new Blob([this.exportedYaml], { type: 'application/x-yaml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = this.exportFilename;
            a.click();
            URL.revokeObjectURL(url);
        },

        async copyYaml() {
            try {
                await navigator.clipboard.writeText(this.exportedYaml);
                alert('已复制到剪贴板');
            } catch (e) {
                alert('复制失败');
            }
        },

        importToClash() {
            if (!this.exportUrl) {
                alert('未找到导出链接');
                return;
            }
            const fullUrl = encodeURIComponent(`${window.location.protocol}//${window.location.host}${this.exportUrl}`);
            const name = encodeURIComponent(this.exportFilename.replace('.yaml', ''));
            // Schema: clash://install-config?url=xxx&name=xxx
            window.location.href = `clash://install-config?url=${fullUrl}&name=${name}`;
        }
    };
}
