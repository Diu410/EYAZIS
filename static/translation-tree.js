(() => {
    'use strict';
    const state = JSON.parse(document.getElementById('syntax-data').textContent);
    const choice = document.getElementById('sentence-choice');
    const build = document.getElementById('build-tree');
    const graph = document.getElementById('sentence-tree');
    const status = document.getElementById('tree-status');
    const controls = document.getElementById('tree-controls');
    const scale = document.getElementById('tree-scale');
    const textPanel = document.getElementById('tree-text-panel');
    const text = document.getElementById('sentence-tree-text');
    const ns = 'http://www.w3.org/2000/svg';
    let naturalWidth = 0;

    function svgElement(name, attributes, content) {
        const element = document.createElementNS(ns, name);
        for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
        if (content !== undefined) element.textContent = content;
        return element;
    }

    function resize() {
        const svg = graph.querySelector('svg');
        if (!svg) return;
        svg.style.width = `${naturalWidth * Number(scale.value) / 100}px`;
        document.getElementById('tree-scale-value').value = `${scale.value}%`;
    }

    function draw(nodes) {
        const measure = document.createElement('canvas').getContext('2d');
        measure.font = '600 16px system-ui';
        const entries = nodes.map((node, index) => ({
            ...node, id: index + 1, children: [],
            boxWidth: Math.max(90, measure.measureText(node.word).width + 30),
        }));
        const roots = [];
        for (const node of entries) {
            if (node.head === 0) roots.push(node);
            else entries[node.head - 1].children.push(node);
        }
        const gap = 20, row = 114, boxHeight = 54, margin = 24;
        function width(node) {
            node.width = Math.max(node.boxWidth, node.children.reduce((sum, child) => sum + width(child), 0)
                + Math.max(0, node.children.length - 1) * gap);
            return node.width;
        }
        naturalWidth = roots.reduce((sum, root) => sum + width(root), 0)
            + Math.max(0, roots.length - 1) * gap + margin * 2;
        let maxDepth = 0;
        function position(node, left, depth) {
            node.x = left + node.width / 2;
            node.y = margin + depth * row;
            maxDepth = Math.max(maxDepth, depth);
            const childrenWidth = node.children.reduce((sum, child) => sum + child.width, 0)
                + Math.max(0, node.children.length - 1) * gap;
            let childLeft = left + (node.width - childrenWidth) / 2;
            for (const child of node.children) {
                position(child, childLeft, depth + 1);
                childLeft += child.width + gap;
            }
        }
        let left = margin;
        for (const root of roots) {
            position(root, left, 0);
            left += root.width + gap;
        }
        const height = margin * 2 + maxDepth * row + boxHeight;
        const svg = svgElement('svg', {viewBox: `0 0 ${naturalWidth} ${height}`, role: 'img',
            'aria-label': 'Дерево синтаксических зависимостей: ' + entries.map(node => node.word).join(' ')});
        svg.append(svgElement('title', {}, 'Дерево синтаксических зависимостей'));
        for (const node of entries) {
            if (!node.head) continue;
            const parent = entries[node.head - 1];
            const joint = parent.y + boxHeight + 24;
            svg.append(svgElement('path', {class: 'tree-edge',
                d: `M ${parent.x} ${parent.y + boxHeight} V ${joint} H ${node.x} V ${node.y}`}));
            svg.append(svgElement('text', {class: 'tree-relation', x: node.x, y: node.y - 9,
                'text-anchor': 'middle'}, node.rel));
        }
        for (const node of entries) {
            const group = svgElement('g', {class: node.head ? 'tree-node' : 'tree-node tree-root'});
            group.append(svgElement('title', {}, `${node.word}: ${node.pos}, ${node.rel}`));
            group.append(svgElement('rect', {x: node.x - node.boxWidth / 2, y: node.y,
                width: node.boxWidth, height: boxHeight, rx: 9}));
            group.append(svgElement('text', {class: 'tree-word', x: node.x, y: node.y + 23,
                'text-anchor': 'middle'}, node.word));
            group.append(svgElement('text', {class: 'tree-pos', x: node.x, y: node.y + 43,
                'text-anchor': 'middle'}, node.pos + (node.head ? '' : ' · ROOT')));
            svg.append(group);
        }
        graph.replaceChildren(svg);
        resize();
    }

    function render() {
        const item = state.sentences[Number(choice?.value || 0)];
        graph.replaceChildren();
        graph.hidden = controls.hidden = !item?.nodes?.length;
        textPanel.hidden = !item?.tree;
        text.textContent = item?.tree || '';
        document.getElementById('tree-sentence').textContent = item?.sentence || '';
        status.textContent = !item ? 'Нет предложений для разбора.' : item.nodes?.length ? ''
            : 'Нажмите «Построить дерево», чтобы показать схему.';
        if (item?.nodes?.length) draw(item.nodes);
    }

    if (choice) {
        choice.value = String(state.selected);
        choice.addEventListener('change', render);
    }
    scale.addEventListener('input', resize);
    document.getElementById('tree-fit').addEventListener('click', () => {
        scale.value = String(Math.max(20, Math.min(150, Math.floor((graph.clientWidth - 16) / naturalWidth * 100))));
        resize();
    });
    build.disabled = !state.sentences.length;
    build.addEventListener('click', async () => {
        const index = Number(choice.value);
        build.disabled = true;
        status.textContent = 'Строится дерево…';
        try {
            const response = await fetch(`/translation/tree/${state.resultId}`, {
                method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: `index=${index}`,
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Не удалось построить дерево.');
            Object.assign(state.sentences[index], result);
            render();
        } catch (error) {
            status.textContent = error.message;
        } finally {
            build.disabled = false;
        }
    });
    render();
})();
